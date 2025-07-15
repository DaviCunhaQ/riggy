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
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdf_canvas
import statistics

# === CONFIGURAÇÕES ===
PORTA_UDP = 5000
TIMEOUT = 0.02
LP_ALPHA = 0.9
TILT_THRESHOLD = 80.0
VIB_THRESHOLD = 1.5
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

tilts_all = []  # <- NOVO: todos os valores de inclinação
vibracoes_all = []  # <- NOVO: todos os valores de vibração

tilt_alerted = False
vib_alerted = False
t = 0
gravity = [0.0, 0.0, 9.81]

# === RELATÓRIO ===
def gerar_relatorio():
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{now}.pdf"
    tilt_list = [v for v in tilts_all if not math.isnan(v)]
    vib_list = [v for v in vibracoes_all if not math.isnan(v)]
    tilt_media = sum(tilt_list) / len(tilt_list) if tilt_list else 0
    vib_media = sum(vib_list) / len(vib_list) if vib_list else 0
    tilt_max = max(tilt_list) if tilt_list else 0
    tilt_min = min(tilt_list) if tilt_list else 0
    vib_max = max(vib_list) if vib_list else 0
    vib_min = min(vib_list) if vib_list else 0
    tilt_std = statistics.stdev(tilt_list) if len(tilt_list) > 1 else 0
    vib_std = statistics.stdev(vib_list) if len(vib_list) > 1 else 0

    c = pdf_canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Relatório - Riggy")
    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Data: {datetime.now():%d/%m/%Y %H:%M:%S}")
    y -= 30
    c.drawString(50, y, f"Pontos recebidos: {len(tempo)}")
    y -= 20
    c.drawString(50, y, f"Alertas de Inclinação: {sum(1 for a in alerts if a[0]=='tilt')}")
    y -= 20
    c.drawString(50, y, f"Alertas de Vibração: {sum(1 for a in alerts if a[0]=='vibração')}")
    y -= 30
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "Inclinação (°):")
    y -= 20
    c.setFont("Helvetica", 12)
    c.drawString(60, y, f"Média: {tilt_media:.2f}")
    y -= 20
    c.drawString(60, y, f"Máximo: {tilt_max:.2f}")
    y -= 20
    c.drawString(60, y, f"Mínimo: {tilt_min:.2f}")
    y -= 20
    c.drawString(60, y, f"Desvio padrão: {tilt_std:.2f}")
    y -= 30
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "Vibração (g):")
    y -= 20
    c.setFont("Helvetica", 12)
    c.drawString(60, y, f"Média: {vib_media:.2f}")
    y -= 20
    c.drawString(60, y, f"Máximo: {vib_max:.2f}")
    y -= 20
    c.drawString(60, y, f"Mínimo: {vib_min:.2f}")
    y -= 20
    c.drawString(60, y, f"Desvio padrão: {vib_std:.2f}")
    y -= 40
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, y, "Gerado por Riggy - UDP SensaGram")
    c.save()
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
        tilts_all.append(tilt_angle)  # <- adicionar ao histórico

        # Vibração com suavização (média móvel)
        total_acc = math.sqrt(ax*ax + ay*ay + az*az)
        vib = abs(total_acc - 9.81)
        vibracoes.append(vib)
        vibracoes_all.append(vib)  # <- adicionar ao histórico
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
ctk.set_default_color_theme('dark-blue')  # Usaremos customização manual para laranja

# Cores customizadas
COR_LARANJA = '#FF8800'
COR_PRETO = '#181818'
COR_CINZA = '#232323'
COR_TEXTO = '#FFFFFF'

app = ctk.CTk()
app.title('Riggy - UDP SensaGram')
app.geometry('900x700')
app.configure(bg=COR_PRETO)

frame = ctk.CTkFrame(app, fg_color=COR_CINZA, corner_radius=16)
frame.pack(padx=30, pady=30, fill='both', expand=True)

status_label = ctk.CTkLabel(frame, text='Pronto', font=('Segoe UI', 16, 'bold'), text_color=COR_LARANJA)
status_label.pack(pady=(10, 20))

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5))
fig.patch.set_facecolor(COR_CINZA)
fig.tight_layout(pad=3.0)
canvas = FigureCanvasTkAgg(fig, frame)
canvas.get_tk_widget().pack(fill='both', expand=True, pady=(0, 10))

# Customização dos gráficos
plt.rcParams['axes.facecolor'] = COR_CINZA
plt.rcParams['figure.facecolor'] = COR_CINZA
plt.rcParams['axes.labelcolor'] = COR_TEXTO
plt.rcParams['xtick.color'] = COR_TEXTO
plt.rcParams['ytick.color'] = COR_TEXTO
plt.rcParams['axes.edgecolor'] = COR_PRETO
plt.rcParams['text.color'] = COR_TEXTO


def update_graph():
    if tilts:
        pts = list(range(len(tilts)))
        ax1.clear()
        ax1.plot(pts, list(tilts), color=COR_LARANJA, linewidth=2)
        ax1.set_ylim(0, 100)
        ax1.set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        ax1.set_ylabel('Grau', color=COR_TEXTO)
        ax1.set_facecolor(COR_CINZA)
    if vibracoes:
        pts = list(range(len(vibracoes)))
        ax2.clear()
        ax2.plot(pts, list(vibracoes), color='#FFB266', linewidth=2)
        ax2.set_ylim(0, 5)
        ax2.set_title('Vibração (g)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        ax2.set_ylabel('g', color=COR_TEXTO)
        ax2.set_facecolor(COR_CINZA)
    canvas.draw()
    if running:
        app.after(50, update_graph)

btn_frame = ctk.CTkFrame(frame, fg_color='transparent')
btn_frame.pack(pady=(10, 0))

# CAMPOS DE ENTRADA DE LIMITES
entry_frame = ctk.CTkFrame(app)
entry_frame.pack(pady=10)

ctk.CTkLabel(entry_frame, text="Limite de inclinação:", font=('Segoe UI', 12)).grid(row=0, column=0, padx=5)
entry_tilt_limit = ctk.CTkEntry(entry_frame, width=60)
entry_tilt_limit.insert(0, "80.0")
entry_tilt_limit.grid(row=0, column=1, padx=5)

ctk.CTkLabel(entry_frame, text="Limite de vibração:", font=('Segoe UI', 12)).grid(row=0, column=2, padx=5)
entry_vib_limit = ctk.CTkEntry(entry_frame, width=60)
entry_vib_limit.insert(0, "1.5")
entry_vib_limit.grid(row=0, column=3, padx=5)

btn_start = ctk.CTkButton(
    btn_frame, text='Iniciar',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=lambda: start_recepcao()
)
btn_start.grid(row=0, column=0, padx=10, pady=10)

btn_report = ctk.CTkButton(
    btn_frame, text='Relatório',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=gerar_relatorio, state='disabled'
)
btn_report.grid(row=0, column=1, padx=10, pady=10)

def start_recepcao():
    global running, thread, TILT_THRESHOLD, VIB_THRESHOLD

    reset_dados()

    # LER LIMITES DIGITADOS
    try:
        TILT_THRESHOLD = float(entry_tilt_limit.get())
    except:
        TILT_THRESHOLD = 80.0  # valor padrão

    try:
        VIB_THRESHOLD = float(entry_vib_limit.get())
    except:
        VIB_THRESHOLD = 1.5  # valor padrão

    running = True
    status_label.configure(text='Recebendo...', text_color=COR_LARANJA)
    btn_start.configure(text='Encerrar', command=stop_recepcao)
    btn_report.configure(state='disabled')
    thread = threading.Thread(target=servidor_udp, daemon=True)
    thread.start()
    update_graph()

def reset_dados():
    global tempo, tilts, vibracoes, alerts, t, gravity, tilt_alerted, vib_alerted, tilts_all, vibracoes_all
    tempo = []
    tilts = deque(maxlen=WINDOW_SIZE)
    vibracoes = deque(maxlen=WINDOW_SIZE)
    alerts = []
    t = 0
    gravity = [0.0, 0.0, 9.81]
    tilt_alerted = False
    vib_alerted = False
    tilts_all = []  # <- resetar histórico
    vibracoes_all = []  # <- resetar histórico

def stop_recepcao():
    global running
    running = False
    status_label.configure(text='Parado', text_color=COR_LARANJA)
    btn_start.configure(text='Iniciar', command=start_recepcao)
    btn_report.configure(text=f'Relatório {datetime.now():%H:%M}', state='normal')

app.mainloop()
