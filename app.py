import eventlet
# 為了更好的非同步性能，建議使用 eventlet 或 gevent
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

# --- 配置 ---
TOTAL_TABLES = 3  # 可在此調整總桌數
NUMBER_RANGE = (1, 100) # 數字範圍

# --- 應用程式初始化 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key' # 正式環境請更換為更複雜的密鑰
socketio = SocketIO(app, async_mode='eventlet')

# --- 遊戲狀態管理 ---
# 使用字典來儲存每桌的狀態
# 結構: {1: {'number': None, 'locked': False, 'sid': None}, 2: {...}, ...}
tables_state = {
    i: {'number': None, 'locked': False, 'sid': None} for i in range(1, TOTAL_TABLES + 1)
}
# 追蹤已經被選走的數字
used_numbers = set()

def get_game_state():
    """返回整個遊戲的狀態"""
    return {
        'tables': tables_state,
        'total_tables': TOTAL_TABLES,
        'all_locked': all(table['locked'] for table in tables_state.values())
    }

def find_winner():
    """找出獲勝者"""
    locked_tables = [
        {'table_id': tid, 'number': tdata['number']}
        for tid, tdata in tables_state.items() if tdata['locked']
    ]
    if not locked_tables:
        return None
    winner = max(locked_tables, key=lambda x: x['number'])
    return winner


# --- HTTP 路由 ---
@app.route('/')
def index():
    """主畫面"""
    return render_template('index.html')

@app.route('/mobile')
def mobile():
    """手機使用者介面"""
    return render_template('mobile.html')


# --- WebSocket 事件處理 ---
@socketio.on('connect')
def handle_connect():
    """當有新的客戶端連線時"""
    print(f"Client connected: {request.sid}")
    # 將目前的遊戲狀態發送給剛連線的客戶端
    emit('update_state', get_game_state())

@socketio.on('disconnect')
def handle_disconnect():
    """當有客戶端離線時"""
    print(f"Client disconnected: {request.sid}")
    # 檢查是否有桌子被這個離線的客戶端佔用，若有則釋放
    for table_id, data in tables_state.items():
        if data['sid'] == request.sid:
            data['sid'] = None
            print(f"Table {table_id} has been released.")
            # 廣播更新後的狀態
            socketio.emit('update_state', get_game_state())
            break

@socketio.on('select_table')
def handle_select_table(data):
    """當使用者在手機上選擇桌號時"""
    table_id = int(data['table_id'])

    # 檢查該桌是否已被佔用
    if tables_state[table_id]['sid'] is not None and tables_state[table_id]['sid'] != request.sid:
        emit('table_in_use', {'table_id': table_id})
        return

    # 檢查是否有其他桌子被此 session ID 佔用，若有則先釋放
    for tid, tdata in tables_state.items():
        if tdata['sid'] == request.sid:
            tdata['sid'] = None

    # 佔用新選擇的桌號
    tables_state[table_id]['sid'] = request.sid
    print(f"Client {request.sid} selected table {table_id}")
    
    # 回傳成功訊息
    emit('table_selected_ok', {'table_id': table_id})
    # 廣播狀態更新
    socketio.emit('update_state', get_game_state())


@socketio.on('stop_number')
def handle_stop_number(data):
    """當使用者按下按鈕鎖定數字時"""
    table_id = int(data['table_id'])
    
    # 權限檢查：只有佔用該桌的 session ID 才能鎖定數字
    if tables_state[table_id]['sid'] != request.sid:
        print(f"Unauthorized attempt to stop table {table_id} by {request.sid}")
        return

    if not tables_state[table_id]['locked']:
        import random
        # 產生一個獨一無二的隨機數
        available_numbers = list(set(range(NUMBER_RANGE[0], NUMBER_RANGE[1] + 1)) - used_numbers)
        if not available_numbers:
            # 如果沒有可用的數字了（理論上桌數小於等於數字數量時不會發生）
            print("Error: No available numbers left!")
            return

        chosen_number = random.choice(available_numbers)
        
        # 更新狀態
        used_numbers.add(chosen_number)
        tables_state[table_id]['number'] = chosen_number
        tables_state[table_id]['locked'] = True
        
        print(f"Table {table_id} locked number {chosen_number}")

        # 廣播更新後的狀態
        socketio.emit('update_state', get_game_state())

        # 檢查是否所有桌次都已完成
        if all(table['locked'] for table in tables_state.values()):
            winner = find_winner()
            print(f"Game Over! Winner is Table {winner['table_id']} with number {winner['number']}")
            # 延遲一點時間再公佈結果，增加戲劇性
            socketio.sleep(2)
            socketio.emit('game_over', {'winner': winner})


@socketio.on('reset_game')
def handle_reset_game():
    """處理管理員重置遊戲的請求"""
    global tables_state, used_numbers
    tables_state = {
        i: {'number': None, 'locked': False, 'sid': None} for i in range(1, TOTAL_TABLES + 1)
    }
    used_numbers = set()
    print("--- GAME RESET by admin ---")
    # 廣播重置信號，讓客戶端可以做特殊處理（例如重新整理）
    socketio.emit('game_restarted')
    # 廣播更新後的狀態
    socketio.emit('update_state', get_game_state())


@socketio.on('reset_table')
def handle_reset_table(data):
    """處理管理員重置單一桌次的請求"""
    table_id = int(data['table_id'])

    if table_id in tables_state:
        table_to_reset = tables_state[table_id]
        client_sid_to_reset = table_to_reset.get('sid') # 在重置前獲取SID

        # 如果該桌有已鎖定的號碼，將其從 used_numbers 中移除
        if table_to_reset['locked'] and table_to_reset['number'] is not None:
            if table_to_reset['number'] in used_numbers:
                used_numbers.remove(table_to_reset['number'])

        # 重置該桌的狀態
        tables_state[table_id] = {'number': None, 'locked': False, 'sid': None}

        print(f"Admin reset table {table_id}")

        # 如果有客戶端在該桌上，強制其重置
        if client_sid_to_reset:
            socketio.emit('force_reset_client', room=client_sid_to_reset)
            print(f"Sent force_reset_client to SID {client_sid_to_reset}")

        # 廣播更新後的狀態
        socketio.emit('update_state', get_game_state())


if __name__ == '__main__':
    print("Server starting on http://0.0.0.0:5000")
    print("Main display: http://<Your-IP>:5000")
    print("Mobile client: http://<Your-IP>:5000/mobile")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
