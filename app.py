import eventlet
# 為了更好的非同步性能，建議使用 eventlet 或 gevent
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random

# --- 配置 ---
# 根據 layout.jpg 的固定桌位定義
TABLE_DEFINITIONS = [
    {'id': 'D6', 'name': '體育', 'group': 'de'}, {'id': 'E6', 'name': '體育', 'group': 'de'}, {'id': 'F6', 'name': '國文', 'group': 'fgi'}, {'id': 'G6', 'name': '國文', 'group': 'fgi'}, {'id': 'H6', 'name': '國文', 'group': 'fgi'}, {'id': 'I6', 'name': '國文', 'group': 'fgi'},
    {'id': 'A5', 'name': '音樂', 'group': 'abc'}, {'id': 'B5', 'name': '美術', 'group': 'abc'}, {'id': 'C5', 'name': '美術', 'group': 'abc'}, {'id': 'D5', 'name': '體育', 'group': 'de'}, {'id': 'E5', 'name': '工教', 'group': 'de'}, {'id': 'F5', 'name': '英語', 'group': 'fgi'}, {'id': 'G5', 'name': '英語', 'group': 'fgi'}, {'id': 'H5', 'name': '英語', 'group': 'fgi'}, {'id': 'I5', 'name': '家政', 'group': 'fgi'}, {'id': 'J5', 'name': '公訓', 'group': 'hj'},
    {'id': 'A4', 'name': '音樂', 'group': 'abc'}, {'id': 'B4', 'name': '美術', 'group': 'abc'}, {'id': 'C4', 'name': '美術', 'group': 'abc'}, {'id': 'D4', 'name': '體育', 'group': 'de'}, {'id': 'E4', 'name': '工教', 'group': 'de'}, {'id': 'F4', 'name': '英語', 'group': 'fgi'}, {'id': 'G4', 'name': '英語', 'group': 'fgi'}, {'id': 'H4', 'name': '教心', 'group': 'hj'}, {'id': 'I4', 'name': '教心', 'group': 'hj'}, {'id': 'J4', 'name': '公訓', 'group': 'hj'},
    {'id': 'A3', 'name': '化學', 'group': 'abc'}, {'id': 'B3', 'name': '化學', 'group': 'abc'}, {'id': 'C3', 'name': '化學', 'group': 'abc'}, {'id': 'D3', 'name': '物理、自然科學研究所', 'group': 'de'}, {'id': 'E3', 'name': '54體育、工教化學、物應', 'group': 'de'}, {'id': 'F3', 'name': '英語', 'group': 'fgi'}, {'id': 'G3', 'name': '英語', 'group': 'fgi'}, {'id': 'H3', 'name': '教心', 'group': 'hj'}, {'id': 'I3', 'name': '教心', 'group': 'hj'}, {'id': 'J3', 'name': '社會', 'group': 'hj'},
    {'id': 'A2', 'name': '生物', 'group': 'abc'}, {'id': 'B2', 'name': '生物', 'group': 'abc'}, {'id': 'C2', 'name': '數學', 'group': 'abc'}, {'id': 'D2', 'name': '54數學', 'group': 'de'}, {'id': 'E2', 'name': '54數學', 'group': 'de'}, {'id': 'F2', 'name': '54英語地理', 'group': 'fgi'}, {'id': 'G2', 'name': '地理', 'group': 'fgi'}, {'id': 'H2', 'name': '教育', 'group': 'hj'}, {'id': 'I2', 'name': '教育', 'group': 'hj'}, {'id': 'J2', 'name': '衛教', 'group': 'hj'},
    {'id': 'A1', 'name': '生物', 'group': 'abc'}, {'id': 'B1', 'name': '數學', 'group': 'abc'}, {'id': 'C1', 'name': '數學', 'group': 'abc'}, {'id': 'D1', 'name': '54數學', 'group': 'de'},
    {'id': 'G1', 'name': '歷史', 'group': 'fgi'}, {'id': 'H1', 'name': '教育', 'group': 'hj'}, {'id': 'I1', 'name': '教育', 'group': 'hj'}, {'id': 'J1', 'name': '衛教', 'group': 'hj'},
    {'id': '主桌', 'name': '主桌', 'group': 'main'},
]
NUMBER_RANGE = (1, 100) # 數字範圍

# --- 應用程式初始化 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key' # 正式環境請更換為更複雜的密鑰
socketio = SocketIO(app, async_mode='eventlet')

# --- 遊戲狀態管理 ---
# 結構: {'A5': {'number': None, 'locked': False, 'sid': None}, 'B5': {...}, ...}
tables_state = {
    table['id']: {'number': None, 'locked': False, 'sid': None} for table in TABLE_DEFINITIONS
}
# 追蹤已經被選走的數字
used_numbers = set()

def get_game_state():
    """返回整個遊戲的狀態"""
    return {
        'tables': tables_state,
        'layout': TABLE_DEFINITIONS,
        'all_locked': all(table['locked'] for table in tables_state.values()),
        'number_range': NUMBER_RANGE
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
            # 將該桌的號碼從 used_numbers 中移除
            if data['locked'] and data['number'] in used_numbers:
                used_numbers.remove(data['number'])
            # 重置該桌狀態
            tables_state[table_id] = {'number': None, 'locked': False, 'sid': None}
            print(f"Table {table_id} has been released due to disconnect.")
            # 廣播更新後的狀態
            socketio.emit('update_state', get_game_state())
            break

@socketio.on('select_table')
def handle_select_table(data):
    """當使用者在手機上選擇桌號時"""
    table_id = data['table_id']

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
    table_id = data['table_id']
    
    # 權限檢查：只有佔用該桌的 session ID 才能鎖定數字
    if tables_state.get(table_id, {}).get('sid') != request.sid:
        print(f"Unauthorized attempt to stop table {table_id} by {request.sid}")
        return

    if not tables_state[table_id]['locked']:
        # 產生一個獨一無二的隨機數
        available_numbers = list(set(range(NUMBER_RANGE[0], NUMBER_RANGE[1] + 1)) - used_numbers)
        if not available_numbers:
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
        table['id']: {'number': None, 'locked': False, 'sid': None} for table in TABLE_DEFINITIONS
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
    table_id = data['table_id']

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


@socketio.on('set_number_range')
def handle_set_number_range(data):
    """設定數字範圍並重置遊戲"""
    global NUMBER_RANGE
    new_range = data.get('range')
    if new_range and isinstance(new_range, list) and len(new_range) == 2:
        NUMBER_RANGE = tuple(new_range)
        print(f"--- Admin set number range to {NUMBER_RANGE} ---")
        # 重置整個遊戲
        handle_reset_game()


if __name__ == '__main__':
    print("Server starting on http://0.0.0.0:5000")
    print("Main display: http://<Your-IP>:5000")
    print("Mobile client: http://<Your-IP>:5000/mobile")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)