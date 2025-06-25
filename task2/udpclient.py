import socket
import struct
import random
import time
import sys
import threading
import pandas as pd

# ======================== 协议首部定义 ========================
# 首部格式说明:
#   - '!' 表示网络字节序 (big-endian)
#   - 'I' 表示4字节无符号整数 (序列号)
#   - 'I' 表示4字节无符号整数 (确认号)
#   - 'B' 表示1字节无符号字符 (标志位)
#   - 'H' 表示2字节无符号短整数 (数据长度)
#   - '1s' 表示1字节填充字段
HEADER_FORMAT = '!IIBH1s'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# ======================== 协议标志位定义 ========================
SYN = 1
ACK = 2
FIN = 4

# ======================== 客户端配置参数 ========================
TOTAL_PACKETS_TO_SEND = 30  #一共要发送的数量
WINDOW_SIZE = 400  
PACKET_SIZE = 80
TIMEOUT = 0.5  # 超时时间0.5秒

# ======================== 全局状态变量 ========================
send_start = 0              # 发送窗口起始位置（字节）
next_seq_num = 0            # 下一个要发送的数据包起始位置
lock = threading.Lock()     # 线程同步锁

# 已发送但未确认的数据包存储结构:
#   key: 序列号 (seq_num)
#   value: 字典包含:
#     'packet': 完整数据包字节
#     'send_time': 发送时间戳
#     'packet_idx': 包序号
packets_unacked = {}

RTT_OK = []                 # 存储成功的往返时间样本
total_send_num = 0          # 总发送数据包计数（含重传）
receiver_active = True      # 接收线程活动标志
acked_packet_num = 0        # 已确认的数据包计数
all_packets_acked = threading.Event()  # 所有包确认完成事件

def pack_header(seq_num, ack_num, flags=0, data_len=0):#打包首部
    return struct.pack(HEADER_FORMAT, seq_num, ack_num, flags, data_len, b'\x00')

def unpack_header(packet):#解包首部
    try:
        return struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
    except struct.error:
        return None, None, None, None, None

def handle_acks(client_socket):#单独在一个线程,用于接收服务器的ACK
    global send_start, RTT_OK, receiver_active, acked_packet_num, next_seq_num
    
    while receiver_active:
        try:
            response, _ = client_socket.recvfrom(1024)
            _, res_ack, res_flags, _, _ = unpack_header(response) #解包
            
            if res_flags and res_flags & ACK:
                with lock:#线程安全锁
                    # GBN协议：任何ACK都表示之前所有包都已收到
                    if res_ack > send_start:   
                        # 移除所有已确认的包
                        for seq in list(packets_unacked.keys()):
                            if send_start <= seq < res_ack:
                                value = packets_unacked.pop(seq)
                                RTT = (time.time() - value['send_time']) * 1000
                                RTT_OK.append(RTT)
                                acked_packet_num += 1
                                print(f"第{value['packet_idx']}个 (Seq={seq}) server端已经收到, RTT是{RTT:.2f} ms")
                                
                        send_start = res_ack
                        #next_seq_num = send_start
                    if acked_packet_num >= TOTAL_PACKETS_TO_SEND:
                        all_packets_acked.set()

        except socket.timeout:
            continue #超时循环等待
        except Exception as e:
            if receiver_active:
                print(f"接收线程出错: {e}")
            break
    print("接收线程已停止")

def main(server_ip, server_port):
    global send_start, next_seq_num, packets_unacked, total_send_num, receiver_active

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_addr = (server_ip, server_port)

    # ========== 第一步：TCP三次握手模拟 ==========
    # 1. 向服务端发送SYN包(第一次握手) 
    client_seq = random.randint(0, 1500)
    SYN_packet = pack_header(client_seq, 0, flags=SYN)
    client_socket.sendto(SYN_packet, server_addr)
    print(f"已成功向 {server_addr} 发送 SYN (Seq={client_seq})")

    # 2. 服务端发送 SYN-ACK(第二次握手)
    try:
        client_socket.settimeout(2.0)
        SYN_ACK_response, _ = client_socket.recvfrom(1024)
        res_seq, res_ack, res_flags, _, _ = unpack_header(SYN_ACK_response)
        
        # 验证 SYN-ACK 包的标志位和确认号
        if res_flags == SYN | ACK and res_ack == client_seq + 1:
            print(f"成功收到 SYN-ACK (Seq={res_seq}, Ack={res_ack})")
            
            # 向服务端发送 ACK(第三次握手)
            send_start = client_seq + 1
            next_seq_num = send_start
            ACK_packet = pack_header(send_start, res_seq + 1, flags=ACK)
            client_socket.sendto(ACK_packet, server_addr)
            print(f"成功发送 ACK (Ack={res_seq + 1}), 与 {server_addr} 的连接建立!")
            
        else:
            print("有错误, 收到的不是 SYN-ACK 包")
            return
    except socket.timeout:
        print("错误: 服务器连接超时")
        return

    # ========== 第二步：数据传输阶段 ==========
    # 生成测试数据包（每个包包含序号和随机填充）
    data_load = []
    for i in range(TOTAL_PACKETS_TO_SEND):
        # 内容为序号
        data_load.append(f"No.{i+1} Packet".ljust(PACKET_SIZE, '.').encode('utf-8'))

    # 开始接收 ACK
    receiver_thread = threading.Thread(
        target=handle_acks, 
        args=(client_socket,),
        daemon=True
    )
    receiver_thread.start()

    cur_packet_idx = 0  # 当前要发送的数据包索引

    try:
        while not all_packets_acked.is_set():
            with lock:  # 获取线程锁
                # 发送窗口内的新数据包(没满且有未发送的)
                while send_start<= next_seq_num and next_seq_num + PACKET_SIZE <= send_start + WINDOW_SIZE and cur_packet_idx < TOTAL_PACKETS_TO_SEND:
                    data = data_load[cur_packet_idx]
                    
                    packet_header = pack_header(next_seq_num, 0, flags=0, data_len=PACKET_SIZE)
                    packet = packet_header + data
                    
                    # 发送并记录包信息
                    packet_info = {
                        'packet': packet,
                        'send_time': time.time(),
                        'packet_idx': cur_packet_idx + 1,
                    }
                    client_socket.sendto(packet, server_addr)
                    packets_unacked[next_seq_num] = packet_info
                    total_send_num += 1

                    print(f"第{packet_info['packet_idx']}个 (Seq={next_seq_num}) client端已经发送")

                    next_seq_num += PACKET_SIZE
                    cur_packet_idx += 1

                # 检查超时包并重传
                current_time = time.time()
                if packets_unacked and current_time - min([info['send_time'] for info in packets_unacked.values()]) > TIMEOUT:
                   print(f"超时, 重传窗口内所有包 (Seq={send_start}~{next_seq_num - 1})")
                   for seq, info in list(packets_unacked.items()):
                       if seq >= send_start and seq + PACKET_SIZE <= send_start + WINDOW_SIZE:
                           info['send_time'] = current_time
                           client_socket.sendto(info['packet'], server_addr)
                           total_send_num += 1
                           print(f"重传第{info['packet_idx']}个 (Seq={seq}) 数据包")
                    
    finally:
        # ========== 第三步：连接关闭（四次挥手） ==========
        # (第一次挥手)
        FIN_packet = pack_header(next_seq_num, 0, flags=FIN)
        client_socket.sendto(FIN_packet, server_addr)
        print(f"已成功向 {server_addr} 发送 FIN (Seq={next_seq_num})")

        # 等待服务端发送 FIN-ACK(这里是将第二次和第三次合并了)
        try:
            client_socket.settimeout(5.0)
            FIN_ACK_res, _ = client_socket.recvfrom(1024)
            _, res_ack, res_flags, _, _ = unpack_header(FIN_ACK_res)
            if res_flags == FIN | ACK:
                print(f"成功收到 FIN-ACK (Ack={res_ack}), 连接正常关闭")
                 
                # (第四次挥手) 客户端发送ACK确认
                FIN_ACK_packet = pack_header(next_seq_num + 1, res_ack, flags=ACK)
                client_socket.sendto(FIN_ACK_packet, server_addr)
                print(f"已成功向 {server_addr} 发送 ACK (Ack={res_ack})")
        
                # 等待一段时间确保服务器收到ACK
                time.sleep(0.1)
                
        except socket.timeout:
            print("警告: 等待服务器 FIN-ACK 超时")

        # 清理资源
        receiver_active = False 
        receiver_thread.join()
        client_socket.close()

       # ========== 第四步：打印统计信息 ==========
        print("\n" + "="*20 + " 【汇总信息】 " + "="*20)
        if total_send_num > 0:
            # 丢包率的定义按题目要求: 30 / 实际发送的udp packet number
            loss_rate = (TOTAL_PACKETS_TO_SEND / total_send_num) * 100
            print(f"丢包率: {loss_rate:.2f}%")

        if RTT_OK:
            RTT_series = pd.Series(RTT_OK)
            print("\n--- RTT 统计 (单位: ms) ---")
            print(f"最大RTT: {RTT_series.max():.2f} ms")
            print(f"最小RTT: {RTT_series.min():.2f} ms")
            print(f"平均RTT: {RTT_series.mean():.2f} ms")
            print(f"RTT标准差: {RTT_series.std():.2f}")
        else:
            print("没有收集到有效的RTT样本。")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"用法: python {sys.argv[0]} <server_ip> <server_port>")
        print(f"示例: python {sys.argv[0]} 127.0.0.1 11111")
        sys.exit(1)
    
    SERVER_IP = sys.argv[1]
    SERVER_PORT = int(sys.argv[2])
    main(SERVER_IP, SERVER_PORT)