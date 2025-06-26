import customtkinter as ctk  #Lib pra interface
import matplotlib.pyplot as plt  #Gera Gráficos
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg #Gera Gráficos
import socket #Recebe dados UDP do wifi
import threading #Cria nucleos de execução
import pygame # Toca áudio
import json #Interpreta Javascript Object Notation
from datetime import datetime # Data e hora
import os #fazer comandos no sistema
from collections import deque
import math # Matemática Básica

# === CONFIGURAÇÕES ===
PORTA_UDP = 5000
TIMEOUT = 0.02            # 20 ms timeout
LP_ALPHA = 0.9            # Gravidade filtro
TILT_THRESHOLD = 80.0     # grau máximo para alerta tilt
WINDOW_SIZE = 20          # média móvel

# === ÁUDIO ===
pygame.mixer.init() # Start gerador de áudio
def tocar_alerta(nome_arquivo):
    if os.path.isfile(nome_arquivo): #Se o arquivo existe
        pygame.mixer.music.load(nome_arquivo)
        pygame.mixer.music.play() # toca o audio

# === VARIÁVEIS GLOBAIS ===
running = False
thread = None

tempo = []
tilts = deque(maxlen=WINDOW_SIZE)
alerts = []
tilt_alerted = False

t = 0
# gravity filter
gravity = [0.0, 0.0, 9.81]

# === FUNÇÃO DE RELATÓRIO ===
def gerar_relatorio():
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{now}.txt"
    with open(filename, 'w') as f:
        f.write(f"Relatório - {datetime.now():%d/%m/%Y %H:%M:%S}\n")
        f.write(f"Pontos: {len(tempo)}\n")
        f.write(f"Alertas tilt: {sum(1 for a in alerts if a[0]=='tilt')}\n")
        f.write("Ocorrências:\n")
        for tipo, instante, val in alerts:
            f.write(f"[{instante:%H:%M:%S}] {tipo}: {val:.1f}°\n")
    try: os.startfile(filename)
    except: pass

# === THREAD DE LEITURA UDP ===
def servidor_udp():
    global t, running, gravity, tilt_alerted
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #inicia o thread UDP
    sock.bind(("0.0.0.0", PORTA_UDP)) # recebe de qualquer IP na porta definida
    sock.settimeout(TIMEOUT) # Seta o timeout
    # calibração
    for _ in range(WINDOW_SIZE):
        if not running: return
        try:
            data, _ = sock.recvfrom(1024)
            obj = json.loads(data.decode())
            if 'accelerometer' in obj.get('type',''):
                ax, ay, az = obj.get('values')[:3]
                gravity[0] = LP_ALPHA*gravity[0] + (1-LP_ALPHA)*ax
                gravity[1] = LP_ALPHA*gravity[1] + (1-LP_ALPHA)*ay
                gravity[2] = LP_ALPHA*gravity[2] + (1-LP_ALPHA)*az
        except:
            pass
    # processamento
    while running:
        try:
            data, _ = sock.recvfrom(1024)
            obj = json.loads(data.decode())
        except:
            continue
        if 'accelerometer' not in obj.get('type',''): continue
        ax, ay, az = obj.get('values')[:3]
        # filtro gravidade
        gravity[0] = LP_ALPHA*gravity[0] + (1-LP_ALPHA)*ax
        gravity[1] = LP_ALPHA*gravity[1] + (1-LP_ALPHA)*ay
        gravity[2] = LP_ALPHA*gravity[2] + (1-LP_ALPHA)*az
        gx, gy, gz = gravity
        mag = math.sqrt(gx*gx + gy*gy + gz*gz)
        cos_t = gz/mag if mag else 1
        cos_t = max(-1.0, min(1.0, cos_t))
        tilt_angle = math.degrees(math.acos(cos_t))
        # armazenar
        tilts.append(tilt_angle)
        tempo.append(t); t+=1
        avg_tilt = sum(tilts)/len(tilts)
        if avg_tilt>=TILT_THRESHOLD and not tilt_alerted:
            alerts.append(('tilt', datetime.now(), avg_tilt))
            tocar_alerta('alerta_inclinacao.mp3')
            tilt_alerted = True
        if avg_tilt<TILT_THRESHOLD-20:
            tilt_alerted = False

# === INTERFACE ===
ctk.set_appearance_mode('dark')
app = ctk.CTk()
app.title('Riggy - UDP SensaGram')
app.geometry('800x600')
frame = ctk.CTkFrame(app)
frame.pack(padx=10,pady=10,fill='both',expand=True)
status_label = ctk.CTkLabel(frame, text='Pronto', font=('Arial',14))
status_label.pack(pady=5)
fig, ax1 = plt.subplots(figsize=(6,3))
canvas = FigureCanvasTkAgg(fig, frame)
canvas.get_tk_widget().pack(fill='both',expand=True)
def update_graph():
    if tilts:
        pts = list(range(len(tilts)))
        ax1.clear()
        ax1.plot(pts, list(tilts))
        ax1.set_ylim(0, 100)
        ax1.set_title('Inclinação (°)')
        canvas.draw()
    if running:
        app.after(50, update_graph)

btn_start = ctk.CTkButton(frame, text='Iniciar', command=lambda:start_recepcao())
btn_start.pack(pady=5)
btn_report = ctk.CTkButton(frame, text='Relatório', command=gerar_relatorio, state='disabled')
btn_report.pack(pady=5)

def reset_dados():
    global tempo, tilts, alerts, t, gravity, tilt_alerted
    tempo=[]; tilts=deque(maxlen=WINDOW_SIZE); alerts=[]; t=0
    gravity=[0.0,0.0,9.81]; tilt_alerted=False

def start_recepcao():
    global running, thread
    reset_dados()
    running=True
    tilt_alerted=False
    status_label.configure(text='Recebendo...')
    btn_start.configure(text='Encerrar', command=stop_recepcao)
    btn_report.configure(state='disabled')
    thread=threading.Thread(target=servidor_udp,daemon=True)
    thread.start()
    update_graph()

def stop_recepcao():
    global running
    running=False
    status_label.configure(text='Parado')
    btn_start.configure(text='Iniciar', command=lambda:start_recepcao())
    btn_report.configure(text=f'Relatório {datetime.now():%H:%M}', state='normal')

app.mainloop()
