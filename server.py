
from dotenv import load_dotenv
from socket import AF_INET, socket, SOCK_STREAM
from threading import Thread
from datetime import datetime
from dateutil import tz
import math
import os
from pyngrok import ngrok
import pandas as pd
import threading


import folium
import http.server
import socketserver


    

def accept_incoming_connections():
    """
    Accepts any incoming client connexion 
    and starts a dedicated thread for each client.
    """
    while True:
        client, client_address = SERVER.accept()
        print('%s:%s has connected.' % client_address)
        
        # Initialize the dictionaries
        addresses[client] = {}
        positions[client] = {}
        
        # Add current client address into adresses
        addresses[client]['address'] = client_address
        Thread(target=handle_client, args=(client,)).start()


def LOGGER(event, filename, ip, client, type, data):
    """
    A logging function to store all input packets, 
    as well as output ones when they are generated.

    There are two types of logs implemented: 
        - a general (info) logger that will keep track of all 
            incoming and outgoing packets,
        - a position (location) logger that will write to a 
            file contianing only results og GPS data
    """
    
    with open(os.path.join('./logs/', filename), 'a+') as log:
        if (event == 'info'):
            # TSV format of: Timestamp, Client IP, IN/OUT, Packet
            logMessage = datetime.now().strftime('%Y/%m/%d %H:%M:%S') + '\t' + ip + '\t' + client + '\t' + type + '\t' + data + '\n'
        elif (event == 'location'):
            # TSV format of: Timestamp, Client IP, Location DateTime, GPS, Validity, Nb Sat, Latitude, Longitude, Accuracy, Speed, Heading
            logMessage = datetime.now().strftime('%Y/%m/%d %H:%M:%S') + '\t' + ip + '\t' + client + '\t' + '\t'.join(list(str(x) for x in data.values())) + '\n'
        log.write(logMessage)


def handle_client(client):
    """
    Takes client socket as argument. 
    Handles a single client connection, by listening indefinitely for packets.
    """
    
    # Initialize dictionaries for that client
    positions[client]['gps'] = {}

    # Keep receiving and analyzing packets until end of time
    # or until device sends disconnection signal
    keepAlive = True
    while (True):

        # Handle socket errors with a try/except approach
        try:
            packet = client.recv(BUFSIZ)
            
            # Only process non-empty packets
            if (len(packet) > 0):
                print('[', addresses[client]['address'][0], ']', 'IN Hex :', packet.hex(), '(length in bytes =', len(packet), ')')
                keepAlive = read_incoming_packet(client, packet)
                LOGGER('info', 'server_log.txt', addresses[client]['address'][0], addresses[client]['imei'], 'IN', packet.hex())
                
                # Disconnect if client sent disconnect signal
                #if (keepAlive is False):
                #    print('[', addresses[client]['address'][0], ']', 'DISCONNECTED: socket was closed by client.')
                #    client.close()
                #    break

            # Close socket if recv() returns 0 bytes, i.e. connection has been closed
            else:
                print('[', addresses[client]['address'][0], ']', 'DISCONNECTED: socket was closed for an unknown reason.')
                client.close()
                break                

        # Something went sideways... close the socket so that it does not hang
        except Exception as e:
            print('[', addresses[client]['address'][0], ']', 'ERROR: socket was closed due to the following exception:')
            print(e)
            client.close()
            break
    print("This thread is now closed.")


def read_incoming_packet(client, packet):
    """
    Handle incoming packets to identify the protocol they are related to,
    and then redirects to response functions that will generate the apropriate 
    packet that should be sent back.
    Actual sending of the response packet will be done by an external function.
    """

    # Convert hex string into list for convenience
    # Strip packet of bits 1 and 2 (start 0x78 0x78) and n-1 and n (end 0x0d 0x0a)
    packet_list = [packet.hex()[i:i+2] for i in range(4, len(packet.hex())-4, 2)]
    
    # DEBUG: Print the role of current packet
    protocol_name = protocol_dict['protocol'][packet_list[1]]
    protocol_method = protocol_dict['response_method'][protocol_name]
    print('The current packet is for protocol:', protocol_name, 'which has method:', protocol_method)
    # Get the protocol name and react accordingly
    if (protocol_name == 'login'):
        r = answer_login(client, packet_list)
    
    elif (protocol_name == 'gps_positioning' or protocol_name == 'gps_offline_positioning'):
        r = answer_gps(client, packet_list)

    elif (protocol_name == 'status'):
        # Status can sometimes carry signal strength and sometimes not
        if (packet_list[0] == '06'): 
            print('[', addresses[client]['address'][0], ']', 'STATUS : Battery =', int(packet_list[2], base=16), '; Sw v. =', int(packet_list[3], base=16), '; Status upload interval =', int(packet_list[4], base=16))
        elif (packet_list[0] == '07'): 
            print('[', addresses[client]['address'][0], ']', 'STATUS : Battery =', int(packet_list[2], base=16), '; Sw v. =', int(packet_list[3], base=16), '; Status upload interval =', int(packet_list[4], base=16), '; Signal strength =', int(packet_list[5], base=16))
        # Exit function without altering anything
        return(True)
    
    elif (protocol_name == 'hibernation'):
        # Exit function returning False to break main while loop in handle_client()
        print('[', addresses[client]['address'][0], ']', 'STATUS : Sent hibernation packet. Disconnecting now.')
        return(False)

    elif (protocol_name == 'setup'):
        # TODO: HANDLE NON-DEFAULT VALUES
        r = answer_setup(packet_list, '0300', '00110001', '000000', '000000', '000000', '00', '000000', '000000', '000000', '00', '0000', '0000', ['', '', ''])

    elif (protocol_name == 'time'):
        r = answer_time(packet_list)

    elif (protocol_name == 'position_upload_interval'):
        r = answer_upload_interval(client, packet_list)


    # Otherwise, return a generic packet based on the current protocol number
    # without any content: 
    #    - reset
    #    - 
    else:
        r = generic_response(packet_list[1])
    
    # Send response to client
    print('[', addresses[client]['address'][0], ']', 'OUT Hex :', r, '(length in bytes =', len(bytes.fromhex(r)), ')')
    send_response(client, r)
    # Return True to avoid failing in main while loop in handle_client()
    return(True)


def answer_login(client, query):
    """
    This function extracts IMEI and Software Version from the login packet. 
    The IMEI and Software Version will be stored into a client dictionary to 
    allow handling of multiple devices at once, in the future.
    
    The client socket is passed as an argument because it is in this packet
    that IMEI is sent and will be stored in the address dictionary.
    """
    
    # Read data: Bits 2 through 9 are IMEI and 10 is software version
    protocol = query[1]
    addresses[client]['imei'] = ''.join(query[2:10])[1:]
    addresses[client]['software_version'] = int(query[10], base=16)

    # DEBUG: Print IMEI and software version
    print("Detected IMEI :", addresses[client]['imei'], "and Sw v. :", addresses[client]['software_version'])

    # Prepare response: in absence of control values, 
    # always accept the client
    response = '01'
    # response = '44'
    r = make_content_response(hex_dict['start'] + hex_dict['start'], protocol, response, hex_dict['stop_1'] + hex_dict['stop_2'])
    return(r)


def answer_setup(query, uploadIntervalSeconds, binarySwitch, alarm1, alarm2, alarm3, dndTimeSwitch, dndTime1, dndTime2, dndTime3, gpsTimeSwitch, gpsTimeStart, gpsTimeStop, phoneNumbers):
    """
    Synchronous setup is initiated by the device who asks the server for 
    instructions.
    These instructions will consists of bits for different flags as well as
    alarm clocks ans emergency phone numbers.
    """
    
    # Read protocol
    protocol = query[1]

    # Convert binarySwitch from byte to hex
    binarySwitch = format(int(binarySwitch, base=2), '02X')

    # Convert phone numbers to 'ASCII' (?) by padding each digit with 3's and concatenate
    for n in range(len(phoneNumbers)):
        phoneNumbers[n] = bytes(phoneNumbers[n], 'UTF-8').hex()
    phoneNumbers = '3B'.join(phoneNumbers)

    # Build response
    response = uploadIntervalSeconds + binarySwitch + alarm1 + alarm2 + alarm3 + dndTimeSwitch + dndTime1 + dndTime2 + dndTime3 + gpsTimeSwitch + gpsTimeStart + gpsTimeStop + phoneNumbers
    r = make_content_response(hex_dict['start'] + hex_dict['start'], protocol, response, hex_dict['stop_1'] + hex_dict['stop_2'])
    return(r)


def answer_time(query):
    """
    Time synchronization is initiated by the device, which expects a response
    contianing current datetime over 7 bytes: YY YY MM DD HH MM SS.
    This function is a wrapper to generate the proper response
    """
    
    # Read protocol
    protocol = query[1]

    # Get current date and time into the pretty-fied hex format
    response = get_hexified_datetime(truncatedYear=False)

    # Build response
    r = make_content_response(hex_dict['start'] + hex_dict['start'], protocol, response, hex_dict['stop_1'] + hex_dict['stop_2'])
    return(r)


def answer_gps(client, query):
    """
    GPS positioning can come into two packets that have the exact same structure, 
    but protocol can be 0x10 (GPS positioning) or 0x11 (Offline GPS positioning)... ?
    Anyway: the structure of these packets is constant, not like GSM or WiFi packets
    """

    # Reset positions lists  and dictionary (carrier) for that client
    positions[client]['gps'] = {}

    # Read protocol
    protocol = query[1]

    # Extract datetime from incoming query to put into the response
    # Datetime is in HEX format here
    # That means it's read as HEX(YY) HEX(MM) HEX(DD) HEX(HH) HEX(MM) HEX(SS)...
    dt = ''.join([ format(int(x, base = 16), '02d') for x in query[2:8] ])
    # GPS DateTime is at UTC timezone: we need to convert it to local, while keeping the same format as a string
    if (dt != '000000000000'): 
        dt = datetime.strftime(datetime.strptime(dt, '%y%m%d%H%M%S').replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal()), '%y%m%d%H%M%S')

    
    # Read in the incoming GPS positioning
    # Byte 8 contains length of packet on 1st char and number of satellites on 2nd char
    gps_data_length = int(query[8][0], base=16)
    gps_nb_sat = int(query[8][1], base=16)
    # Latitude and longitude are both on 4 bytes, and were multiplied by 30000
    # after being converted to seconds-of-angle. Let's convert them back to degree
    gps_latitude = int(''.join(query[9:13]), base=16) / (30000 * 60)
    gps_longitude = int(''.join(query[13:17]), base=16) / (30000 * 60)
    # Speed is on the next byte
    gps_speed = int(query[17], base=16)
    # Last two bytes contain flags in binary that will be interpreted
    gps_flags = format(int(''.join(query[18:20]), base=16), '0>16b')
    position_is_valid = gps_flags[3]
    # Flip sign of GPS latitude if South, longitude if West
    if (gps_flags[4] == '1'):
        gps_latitude = -gps_latitude
    if (gps_flags[5] == '0'):
        gps_longitude = -gps_longitude
    gps_heading = int(''.join(gps_flags[6:]), base = 2)

    # Store GPS information into the position dictionary and print them
    positions[client]['gps']['method'] = 'GPS'
    # In some cases dt is empty with value '000000000000': let's avoid that because it'll crash strptime
    positions[client]['gps']['datetime'] = datetime.strptime(datetime.now().strftime('%y%m%d%H%M%S') if dt == '000000000000' else dt, '%y%m%d%H%M%S').strftime('%Y/%m/%d %H:%M:%S')
    positions[client]['gps']['valid'] = position_is_valid
    positions[client]['gps']['nb_sat'] = gps_nb_sat
    positions[client]['gps']['latitude'] = gps_latitude
    positions[client]['gps']['longitude'] = gps_longitude
    positions[client]['gps']['accuracy'] = 0.0
    positions[client]['gps']['speed'] = gps_speed
    positions[client]['gps']['heading'] = gps_heading
    print('[', addresses[client]['address'][0], ']', "POSITION/GPS : Valid =", position_is_valid, "; Nb Sat =", gps_nb_sat, "; Lat =", gps_latitude, "; Long =", gps_longitude, "; Speed =", gps_speed, "; Heading =", gps_heading)
    LOGGER('location', 'location_log.txt', addresses[client]['address'][0], addresses[client]['imei'], '', positions[client]['gps'])
    # Get current datetime for answering
    response = get_hexified_datetime(truncatedYear=True)
    r = make_content_response(hex_dict['start'] + hex_dict['start'], protocol, response, hex_dict['stop_1'] + hex_dict['stop_2'])
    return(r)


def answer_upload_interval(client, query):
    """
    Whenever the device received an SMS that changes the value of an upload interval,
    it sends this information to the server.
    The server should answer with the exact same content to acknowledge the packet.
    """

    # Read protocol
    protocol = query[1]

    # Response is new upload interval reported by device (HEX formatted, no need to alter it)
    response = ''.join(query[2:4])

    r = make_content_response(hex_dict['start'] + hex_dict['start'], protocol, response, hex_dict['stop_1'] + hex_dict['stop_2'])
    return(r)


def generic_response(protocol):
    """
    Many queries made by the device do not expect a complex
    response: most of the times, the device expects the exact same packet.
    Here, we will answer fith the same value of protocol that the device sent, 
    not using any content.
    """
    r = make_content_response(hex_dict['start'] + hex_dict['start'], protocol, None, hex_dict['stop_1'] + hex_dict['stop_2'])
    return(r)


def make_content_response(start, protocol, content, stop):
    """
    This is just a wrapper to generate the complete response
    to a query, goven its content.
    It will apply to all packets where response is of the format:
    start-start-length-protocol-content-stop_1-stop_2.
    Other specific packets where length is replaced by counters
    will be treated separately.
    """
    return(start + format((len(bytes.fromhex(content)) if content else 0)+1, '02X') + protocol + (content if content else '') + stop)


def send_response(client, response):
    """
    Function to send a response packet to the client.
    """
    LOGGER('info', 'server_log.txt', addresses[client]['address'][0], addresses[client]['imei'], 'OUT', response)
    client.send(bytes.fromhex(response))


def get_hexified_datetime(truncatedYear):
    """
    Make a fancy function that will return current GMT datetime as hex
    concatenated data, using 2 bytes for year and 1 for the rest.
    The returned string is YY YY MM DD HH MM SS if truncatedYear is False,
    or just YY MM DD HH MM SS if truncatedYear is True.
    """

    # Get current GMT time into a list
    if (truncatedYear):
        dt = datetime.utcnow().strftime('%y-%m-%d-%H-%M-%S').split("-")
    else:
        dt = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S').split("-")

    # Then convert to hex with 2 bytes for year and 1 for the rest
    dt = [ format(int(x), '0'+str(len(x))+'X') for x in dt ]
    return(''.join(dt))



def dot_map():
    '''Creating dot map using folium library. Making htlm file'''
    df = pd.read_csv('logs/location_log.txt', header=None,sep='	')
    m = folium.Map(location=[0,0], tiles='Stamen Toner', zoom_start=15)
    lat=float(df.tail(1)[7])
    lon=float(df.tail(1)[8])
    m = folium.Map([lat,lon], zoom_start=19)
    for i,row in df.iterrows():
        folium.CircleMarker((df[7][i],df[8][i]), radius=3, weight=2, color='red', fill_color='red', fill_opacity=.5).add_to(m)
    m.save('Map.html')


  
def map_to_html_line():
    '''Creating line map using folium library. Making htlm file'''  
    df = pd.read_csv('logs/location_log.txt', header=None,sep='	')
    m = folium.Map(location=[0,0], tiles='Stamen Toner', zoom_start=15)
    lat=float(df.tail(1)[7])
    lon=float(df.tail(1)[8])
    m = folium.Map([lat,lon], zoom_start=19)
    color_line = features.ColorLine(
    positions=list(zip(df[7].tolist(), df[8].tolist())),colors=range(0, len(df[7])),weight=10)
    color_line.add_to(m)
    m.save('Map_line.html')

    
def start_ngrok():
    '''Open a ssh tunel to static wan ip address, requires ngrok api key'''
    ssh_url = ngrok.connect(PORT, "tcp")
    print('static ip address :',ssh_url)





# Declare common Hex codes for packets
hex_dict = {
    'start': '78', 
    'stop_1': '0D', 
    'stop_2': '0A'
}

protocol_dict = {
    'protocol': {
        '01': 'login',
        '05': 'supervision',
        '08': 'heartbeat', 
        '10': 'gps_positioning', 
        '11': 'gps_offline_positioning', 
        '13': 'status', 
        '14': 'hibernation', 
        '15': 'reset', 
        '16': 'whitelist_total', 
        '17': 'wifi_offline_positioning', 
        '30': 'time', 
        '43': 'mom_phone_WTFISDIS?', 
        '56': 'stop_alarm', 
        '57': 'setup', 
        '58': 'synchronous_whitelist', 
        '67': 'restore_password', 
        '69': 'wifi_positioning', 
        '80': 'manual_positioning', 
        '81': 'battery_charge', 
        '82': 'charger_connected', 
        '83': 'charger_disconnected', 
        '94': 'vibration_received', 
        '98': 'position_upload_interval'
    }, 
    'response_method': {
        'login': 'login',
        'logout': 'logout', 
        'supervision': '',
        'heartbeat': '', 
        'gps_positioning': 'datetime_response', 
        'gps_offline_positioning': 'datetime_response', 
        'status': '', 
        'hibernation': '', 
        'reset': '', 
        'whitelist_total': '', 
        'wifi_offline_positioning': 'datetime_position_response', 
        'time': 'time_response', 
        'stop_alarm': '', 
        'setup': 'setup', 
        'synchronous_whitelist': '', 
        'restore_password': '', 
        'wifi_positioning': 'datetime_position_response', 
        'manual_positioning': '', 
        'battery_charge': '', 
        'charger_connected': '', 
        'charger_disconnected': '', 
        'vibration_received': '', 
        'position_upload_interval': 'upload_interval_response'
    }
}

# Import dotenv with API keys and initialize API connections
load_dotenv()

# Details about host server
HOST ='0.0.0.0'
PORT =60000
BUFSIZ = 4096
ADDR = (HOST, PORT)

# Initialize socket
SERVER = socket(AF_INET, SOCK_STREAM)
SERVER.bind(ADDR)
# Store client data into dictionaries
addresses = {}
positions = {}



if __name__ == '__main__':
    #start_ngrok()
    SERVER.listen(5)
    print("Waiting for connection...")
    t1 = threading.Thread(target=accept_incoming_connections)
    t1.start()
    t1.join()
    SERVER.close()
        
    
    
    