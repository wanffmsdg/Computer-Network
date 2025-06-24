import socket
import struct
import random
import time

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

# ======================== 服务器配置参数 ========================
HOST = '127.0.0.1'
PORT = 11111
PACKET_LOSS_RATE = 0.3  # 30%的丢包率

def pack_header(seq_num, ack_num, flags=0, data_len=0):#用于打包首部
    return struct.pack(HEADER_FORMAT, seq_num, ack_num, flags, data_len, b'\x00')

def unpack_header(packet):#用于解包首部
    try:
        return struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
    except struct.error:
        return None, None, None, None, None

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, PORT))
    print("The server is up, waiting to connect...")
    print(f"PACKET_LOSS_RATE is: {PACKET_LOSS_RATE * 100}%")

    # 表示服务器状态
    client_addr = None
    is_connected = False
    expected_seq_num = 0
    
    # 缓冲区:处理乱序包(键:seq, 值:数据长度)
    disorder_buffer = {}

    while True:
        try:
            packet, addr = server_socket.recvfrom(1024)

            # 随机丢包
            if is_connected:
                if random.random() < PACKET_LOSS_RATE:#小于丢包率才丢
                    header_info = unpack_header(packet)
                    if header_info[2] not in [SYN, FIN]:
                        "'数据传输才丢包'"
                        print(f"随机丢弃了来自 {addr} 的 Seq={header_info[0]} 包")
                        continue
            
            seq_num, ack_num, flags, data_len, _ = unpack_header(packet)

            # 1. 连接建立(第一次握手)
            if not is_connected:
                if flags & SYN:
                    print(f"有一个来自 {addr} 的 SYN 连接请求 (Seq={seq_num})")
                    client_addr = addr
                    
                    # 向客户端回复 SYN-ACK(第二次握手)
                    server_seq = random.randint(0, 1500)
                    expected_seq_num = seq_num + 1
                    
                    SYN_ACK_header = pack_header(server_seq, expected_seq_num, flags=SYN|ACK)
                    server_socket.sendto(SYN_ACK_header, client_addr)
                    print(f"已成功向 {client_addr} 发送 SYN-ACK (Seq={server_seq}, Ack={expected_seq_num})")
                    continue

            # 客户端收到 SYN-ACK 后给服务器发送 ACK(第三次握手)
            if not is_connected:
                if flags & ACK:
                    print(f"成功与 {client_addr} 建立连接! (Ack={ack_num})")
                    is_connected = True
                    continue

            # 2. 数据传输阶段
            if is_connected:
                if flags & FIN:
                    print(f"{client_addr} 发送了一个 FIN 包 (Seq={seq_num})")
                    # 向客户端发送 FIN-ACK
                    FIN_ACK_header = pack_header(0, seq_num + 1, flags=FIN|ACK)
                    server_socket.sendto(FIN_ACK_header, client_addr)
                    print(f"已成功向 {client_addr} 发送 FIN-ACK (Ack={seq_num + 1})")
                    
                    try:
                        server_socket.settimeout(5.0)
                        ack_packet, _ = server_socket.recvfrom(1024)
                        _, ack_num, ack_flags, _, _ = unpack_header(ack_packet)
                        if ack_flags & ACK:
                            print(f"收到客户端ACK确认 (Ack={ack_num})")
                    except socket.timeout:
                        print("警告: 等待客户端ACK超时")
                    
                    # 刷新状态变量
                    client_addr = None
                    is_connected = False
                    expected_seq_num = 0
                    disorder_buffer.clear()
                    print(f"The connection with {client_addr} has been dropped...")
                    continue

                # 收到了想要的包
                if seq_num == expected_seq_num:
                    expected_seq_num += data_len
                    ''' 缓存区中可能有后面的包(比如当前的被丢包后再发送就会晚到),
                        所以顺便检查了'''
                    while expected_seq_num in disorder_buffer:
                        print(f"从缓冲区中取出 Seq={expected_seq_num} 的包并处理")
                        buffered_data_len = disorder_buffer.pop(expected_seq_num)
                        expected_seq_num += buffered_data_len

                # 如果后面的包先到了
                elif seq_num > expected_seq_num:
                    if seq_num not in disorder_buffer:
                        disorder_buffer[seq_num] = data_len
                        print(f"有一个后面的包 (Seq={seq_num}) 存入了缓冲区")
                    else:
                        print(f"Seq={seq_num}的包多次到达, 已忽略")

                #累计确认
                server_time = time.time()
                ack_payload = struct.pack('!d', server_time) # 将时间戳打包为8字节double
                ack_header = pack_header(0, expected_seq_num, flags=ACK, data_len=len(ack_payload))
                ack_packet = ack_header + ack_payload
                server_socket.sendto(ack_packet, client_addr)
                print(f"成功向 {client_addr} 发送累计确认 (Ack={expected_seq_num})")

        except Exception as e:
            print(f"服务器出错: {e}")
            break

    server_socket.close()
    print("服务器已关闭。")

if __name__ == '__main__':
    main()