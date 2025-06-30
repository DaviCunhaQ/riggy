import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import socket
import threading
import pygame
import json
from datetime import datetime
import os
from collections import deque
import math

# === CONFIGURAÇÕES ===
PORTA_UDP = 5000
TIMEOUT = 0.02
LP_ALPHA = 0.9
TILT_THRESHOLD = 80.0
VIB_THRESHOLD = 1.5  # alerta se vibração for maior que isso
WINDOW_SIZE = 20

# === ÁUDIO ===
pygame.mixer.init()
def tocar_alerta(nome_arquivo):
    if os.path.isfile(nome_arquivo):
        pygame.mixer.music.load(nome_arquivo)
        pygame.mixer.music.play()

# === VARIÁVEIS GLOBAIS ===
running = False
thread = None

tempo = []
tilts = deque(maxlen=WINDOW_SIZE)
vibracoes = deque(maxlen=WINDOW_SIZE)
alerts = []

tilt_alerted = False
vib_alerted = False
t = 0
gravity = [0.0, 0.0, 9.81]

# === RELATÓRIO ===
def gerar_relatorio():
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{now}.txt"
    with open(filename, 'w') as f:
        f.write(f"Relatório - {datetime.now():%d/%m/%Y %H:%M:%S}\n\n")
        f.write(f"Pontos recebidos: {len(tempo)}\n")
        f.write(f"Alertas de Inclinação: {sum(1 for a in alerts if a[0]=='tilt')}\n")
        f.write(f"Alertas de Vibração: {sum(1 for a in alerts if a[0]=='vibração')}\n\n")
        tilt_media = sum(tilts) / len(tilts) if tilts else 0
        vib_media = sum(vibracoes) / len(vibracoes) if vibracoes else 0
        f.write(f"Inclinação média: {tilt_media:.2f}°\n")
        f.write(f"Vibração média: {vib_media:.2f} g\n")
    try:
        os.startfile(filename)
    except:
        pass


# === THREAD UDP ===
def servidor_udp():
    global t, running, gravity, tilt_alerted, vib_alerted
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORTA_UDP))
    sock.settimeout(TIMEOUT)

    # Calibração da gravidade
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

    while running:
        try:
            data, _ = sock.recvfrom(1024)
            obj = json.loads(data.decode())
        except:
            continue

        if 'accelerometer' not in obj.get('type',''):
            continue

        ax, ay, az = obj.get('values')[:3]

        # Filtro de gravidade
        gravity[0] = LP_ALPHA*gravity[0] + (1-LP_ALPHA)*ax
        gravity[1] = LP_ALPHA*gravity[1] + (1-LP_ALPHA)*ay
        gravity[2] = LP_ALPHA*gravity[2] + (1-LP_ALPHA)*az
        gx, gy, gz = gravity

        # Inclinação
        mag = math.sqrt(gx*gx + gy*gy + gz*gz)
        cos_t = gz/mag if mag else 1
        cos_t = max(-1.0, min(1.0, cos_t))
        tilt_angle = math.degrees(math.acos(cos_t))
        tilts.append(tilt_angle)

        # Vibração com suavização (média móvel)
        total_acc = math.sqrt(ax*ax + ay*ay + az*az)
        vib = abs(total_acc - 9.81)
        vibracoes.append(vib)
        avg_vib = sum(vibracoes) / len(vibracoes)

        tempo.append(t)
        t += 1

        # Alerta de inclinação (baseado na média)
        avg_tilt = sum(tilts) / len(tilts)
        if avg_tilt >= TILT_THRESHOLD and not tilt_alerted:
            alerts.append(('tilt', datetime.now(), avg_tilt))
            tocar_alerta('alerta_inclinacao.mp3')
            tilt_alerted = True
        if avg_tilt < TILT_THRESHOLD - 20:
            tilt_alerted = False

        # Alerta de vibração (baseado na média)
        if avg_vib >= VIB_THRESHOLD and not vib_alerted:
            alerts.append(('vibração', datetime.now(), avg_vib))
            tocar_alerta('alerta_vibracao.mp3')
            vib_alerted = True
        if avg_vib < VIB_THRESHOLD - 0.3:
            vib_alerted = False


# === INTERFACE ===
ctk.set_appearance_mode('dark')
app = ctk.CTk()
app.title('Riggy - UDP SensaGram')
app.geometry('900x700')

frame = ctk.CTkFrame(app)
frame.pack(padx=10, pady=10, fill='both', expand=True)

status_label = ctk.CTkLabel(frame, text='Pronto', font=('Arial', 14))
status_label.pack(pady=5)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5))
fig.tight_layout(pad=3.0)
canvas = FigureCanvasTkAgg(fig, frame)
canvas.get_tk_widget().pack(fill='both', expand=True)

def update_graph():
    if tilts:
        pts = list(range(len(tilts)))
        ax1.clear()
        ax1.plot(pts, list(tilts), color='orange')
        ax1.set_ylim(0, 100)
        ax1.set_title('Inclinação (°)')
        ax1.set_ylabel('Grau')
    if vibracoes:
        pts = list(range(len(vibracoes)))
        ax2.clear()
        ax2.plot(pts, list(vibracoes), color='cyan')
        ax2.set_ylim(0, 5)
        ax2.set_title('Vibração (g)')
        ax2.set_ylabel('g')
    canvas.draw()
    if running:
        app.after(50, update_graph)

btn_start = ctk.CTkButton(frame, text='Iniciar', command=lambda: start_recepcao())
btn_start.pack(pady=5)

btn_report = ctk.CTkButton(frame, text='Relatório', command=gerar_relatorio, state='disabled')
btn_report.pack(pady=5)

def reset_dados():
    global tempo, tilts, vibracoes, alerts, t, gravity, tilt_alerted, vib_alerted
    tempo = []
    tilts = deque(maxlen=WINDOW_SIZE)
    vibracoes = deque(maxlen=WINDOW_SIZE)
    alerts = []
    t = 0
    gravity = [0.0, 0.0, 9.81]
    tilt_alerted = False
    vib_alerted = False

def start_recepcao():
    global running, thread
    reset_dados()
    running = True
    status_label.configure(text='Recebendo...')
    btn_start.configure(text='Encerrar', command=stop_recepcao)
    btn_report.configure(state='disabled')
    thread = threading.Thread(target=servidor_udp, daemon=True)
    thread.start()
    update_graph()

def stop_recepcao():
    global running
    running = False
    status_label.configure(text='Parado')
    btn_start.configure(text='Iniciar', command=start_recepcao)
    btn_report.configure(text=f'Relatório {datetime.now():%H:%M}', state='normal')

app.mainloop()
