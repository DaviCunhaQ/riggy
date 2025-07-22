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
import subprocess
import re

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
    tilt_list = [v for v in tilts_all if not math.isnan(v)] if grafico_tilt_var.get() else []
    vib_list = [v for v in vibracoes_all if not math.isnan(v)] if grafico_vib_var.get() else []
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
    # Adiciona o logo no topo do PDF, agora alinhado à esquerda
    logo_path = os.path.join(os.path.dirname(__file__), 'riggy-logo.jpeg')
    if os.path.isfile(logo_path):
        logo_width = 80
        logo_height = 80
        c.drawImage(logo_path, 40, height - logo_height - 20, width=logo_width, height=logo_height, mask='auto')
        y = height - logo_height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Relatório - Riggy")
    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Data: {datetime.now():%d/%m/%Y %H:%M:%S}")
    y -= 30
    c.drawString(50, y, f"Pontos recebidos: {len(tempo)}")
    y -= 20
    c.drawString(50, y, f"Alertas de Inclinação: {sum(1 for a in alerts if a[0]=='tilt') if grafico_tilt_var.get() else 0}")
    y -= 20
    c.drawString(50, y, f"Alertas de Vibração: {sum(1 for a in alerts if a[0]=='vibração') if grafico_vib_var.get() else 0}")
    if grafico_tilt_var.get():
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
    if grafico_vib_var.get():
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
        tilts_all.append(tilt_angle)

        # Vibração com suavização (média móvel)
        total_acc = math.sqrt(ax*ax + ay*ay + az*az)
        vib = abs(total_acc - 9.81)
        vibracoes.append(vib)
        vibracoes_all.append(vib)
        avg_vib = sum(vibracoes) / len(vibracoes) if vibracoes else 0

        tempo.append(t)
        t += 1

        # Alerta de inclinação (baseado na média)
        if grafico_tilt_var.get():
            avg_tilt = sum(tilts) / len(tilts) if tilts else 0
            if avg_tilt >= TILT_THRESHOLD and not tilt_alerted:
                alerts.append(('tilt', datetime.now(), avg_tilt))
                tocar_alerta('alerta_inclinacao.mp3')
                tilt_alerted = True
            if avg_tilt < TILT_THRESHOLD - 20:
                tilt_alerted = False

        # Alerta de vibração (baseado na média)
        if grafico_vib_var.get():
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
# Define o ícone da janela, se disponível
ico_path = os.path.join(os.path.dirname(__file__), 'riggy-logo.ico')
if os.path.isfile(ico_path):
    try:
        app.iconbitmap(ico_path)
    except Exception:
        pass

# Função para obter o IP local preferencialmente do Wi-Fi
import sys
import platform

def get_local_ip():
    try:
        # Método universal: conecta a um IP externo e pega o IP local usado
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            # Não precisa estar online, só resolve a interface local
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def get_wifi_ssid():
    if os.name == 'nt':  # Windows
        try:
            output = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces'], encoding='utf-8', errors='ignore')
            for line in output.split('\n'):
                if 'SSID' in line and 'BSSID' not in line:
                    ssid = line.split(':', 1)[1].strip()
                    if ssid and ssid.lower() != 'ssid':
                        return ssid
        except Exception:
            pass
    return 'N/A'

# ===== NOVO LAYOUT PRINCIPAL =====
# Frame do título
frame_titulo = ctk.CTkFrame(app, fg_color='transparent')
frame_titulo.pack(fill='x', pady=(10, 0))
label_titulo = ctk.CTkLabel(frame_titulo, text='Riggy', font=('Segoe UI', 24, 'bold'), text_color=COR_LARANJA)
label_titulo.pack(anchor='center')

# Adiciona o label de IP, porta e Wi-Fi logo abaixo do título
local_ip = get_local_ip()
wifi_ssid = get_wifi_ssid()
label_ip = ctk.CTkLabel(frame_titulo, text=f'ip: {local_ip}  port: {PORTA_UDP}  wifi: {wifi_ssid}', font=('Segoe UI', 14), text_color=COR_TEXTO)
label_ip.pack(anchor='center', pady=(2, 0))

# Frame principal dividido (esquerda/direita)
frame_principal = ctk.CTkFrame(app, fg_color='transparent')
frame_principal.pack(fill='both', expand=True, padx=20, pady=10)

# Frame esquerdo (controles)
frame_esquerdo = ctk.CTkFrame(frame_principal, fg_color=COR_CINZA, corner_radius=16, width=300)
frame_esquerdo.pack(side='left', fill='y', padx=(0, 20), pady=0)
frame_esquerdo.pack_propagate(False)

# Frame direito (conteúdo)
frame_direito = ctk.CTkFrame(frame_principal, fg_color=COR_CINZA, corner_radius=16)
frame_direito.pack(side='right', fill='both', expand=True, pady=0)

# ===== FIM NOVO LAYOUT PRINCIPAL =====

# (O restante da interface será migrado para os novos frames nas próximas etapas)

# ===== ABA SUPERIOR: CHECKBOXES DE GRÁFICOS =====
checkbox_frame = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
checkbox_frame.pack(fill='x', pady=(10, 0))

# Variáveis de controle dos checkboxes
grafico_tilt_var = ctk.BooleanVar(value=False)
grafico_vib_var = ctk.BooleanVar(value=False)

def on_checkbox_change():
    atualizar_inputs_limites()
    atualizar_estado_iniciar()
    update_graph()

checkbox_tilt = ctk.CTkCheckBox(
    checkbox_frame, text='Inclinação', variable=grafico_tilt_var,
    command=on_checkbox_change, font=('Segoe UI', 13), text_color=COR_TEXTO
)
checkbox_tilt.pack(side='left', padx=10, pady=5)

checkbox_vib = ctk.CTkCheckBox(
    checkbox_frame, text='Vibração', variable=grafico_vib_var,
    command=on_checkbox_change, font=('Segoe UI', 13), text_color=COR_TEXTO
)
checkbox_vib.pack(side='left', padx=10, pady=5)
# ===== FIM ABA SUPERIOR =====

status_label = ctk.CTkLabel(frame_esquerdo, text='Pronto para iniciar', font=('Segoe UI', 16, 'bold'), text_color=COR_LARANJA)
status_label.pack(pady=(10, 20))

# Subplots dinâmicos
fig, axs = plt.subplots(2, 1, figsize=(7, 5))
fig.patch.set_facecolor(COR_CINZA)
fig.tight_layout(pad=3.0)
canvas = FigureCanvasTkAgg(fig, frame_direito)

# Customização dos gráficos
plt.rcParams['axes.facecolor'] = COR_CINZA
plt.rcParams['figure.facecolor'] = COR_CINZA
plt.rcParams['axes.labelcolor'] = COR_TEXTO
plt.rcParams['xtick.color'] = COR_TEXTO
plt.rcParams['ytick.color'] = COR_TEXTO
plt.rcParams['axes.edgecolor'] = COR_PRETO
plt.rcParams['text.color'] = COR_TEXTO


# Função para atualizar os gráficos exibidos

def update_graph():
    # Limpa todos os eixos
    for ax in axs:
        ax.clear()
        ax.set_visible(False)  # Oculta todos inicialmente

    show_tilt = grafico_tilt_var.get()
    show_vib = grafico_vib_var.get()

    if not show_tilt and not show_vib:
        canvas.draw()
        if running:
            app.after(50, update_graph)
        return

    if show_tilt and show_vib:
        # Dois gráficos: tilt em axs[0], vib em axs[1]
        axs[0].set_visible(True)
        axs[1].set_visible(True)
        if tilts:
            pts = list(range(len(tilts)))
            axs[0].plot(pts, list(tilts), color=COR_LARANJA, linewidth=2)
        axs[0].set_ylim(0, 100)
        axs[0].set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('Grau', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

        if vibracoes:
            pts = list(range(len(vibracoes)))
            axs[1].plot(pts, list(vibracoes), color='#FFB266', linewidth=2)
        axs[1].set_ylim(0, 5)
        axs[1].set_title('Vibração (g)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[1].set_ylabel('g', color=COR_TEXTO)
        axs[1].set_facecolor(COR_CINZA)

    elif show_tilt:
        axs[0].set_visible(True)
        if tilts:
            pts = list(range(len(tilts)))
            axs[0].plot(pts, list(tilts), color=COR_LARANJA, linewidth=2)
        axs[0].set_ylim(0, 100)
        axs[0].set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('Grau', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

    elif show_vib:
        axs[0].set_visible(True)
        if vibracoes:
            pts = list(range(len(vibracoes)))
            axs[0].plot(pts, list(vibracoes), color='#FFB266', linewidth=2)
        axs[0].set_ylim(0, 5)
        axs[0].set_title('Vibração (g)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('g', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

    fig.tight_layout(pad=3.0)
    canvas.draw()
    if running:
        app.after(50, update_graph)

# Atualizar gráficos ao mudar seleção dos checkboxes
grafico_tilt_var.trace_add('write', lambda *a: update_graph())
grafico_vib_var.trace_add('write', lambda *a: update_graph())

btn_frame = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
btn_frame.pack(pady=(10, 0))

# ===== ABA INFERIOR: INPUTS DE LIMITES DINÂMICOS =====
frame_limites = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
frame_limites.pack(fill='x', pady=(10, 0))

# Variáveis dos inputs
entry_tilt_limit = None
entry_vib_limit = None
label_tilt = None
label_vib = None
label_nenhum = None

# Função para checar se pode habilitar o botão iniciar
def pode_iniciar():
    # Pelo menos um gráfico selecionado
    if not grafico_tilt_var.get() and not grafico_vib_var.get():
        return False
    # Se inclinação selecionada, input preenchido e válido
    if grafico_tilt_var.get():
        if not entry_tilt_limit or not entry_tilt_limit.get().strip():
            return False
        try:
            float(entry_tilt_limit.get())
        except:
            return False
    # Se vibração selecionada, input preenchido e válido
    if grafico_vib_var.get():
        if not entry_vib_limit or not entry_vib_limit.get().strip():
            return False
        try:
            float(entry_vib_limit.get())
        except:
            return False
    return True

# Atualiza o estado do botão iniciar
def atualizar_estado_iniciar(*args):
    if pode_iniciar():
        btn_start.configure(state='normal')
    else:
        btn_start.configure(state='disabled')

# Modificar atualizar_inputs_limites para conectar eventos dos inputs
def atualizar_inputs_limites():
    global entry_tilt_limit, entry_vib_limit, label_tilt, label_vib, label_nenhum
    for widget in frame_limites.winfo_children():
        widget.destroy()
    entry_tilt_limit = None
    entry_vib_limit = None
    label_tilt = None
    label_vib = None
    label_nenhum = None
    if grafico_tilt_var.get():
        label_tilt = ctk.CTkLabel(frame_limites, text="Limite de inclinação:", font=('Segoe UI', 12))
        label_tilt.pack(pady=(0, 2))
        entry_tilt_limit = ctk.CTkEntry(frame_limites, width=60)
        entry_tilt_limit.insert(0, "80.0")
        entry_tilt_limit.pack(pady=(0, 8))
        entry_tilt_limit.bind('<KeyRelease>', lambda e: atualizar_estado_iniciar())
    if grafico_vib_var.get():
        label_vib = ctk.CTkLabel(frame_limites, text="Limite de vibração:", font=('Segoe UI', 12))
        label_vib.pack(pady=(0, 2))
        entry_vib_limit = ctk.CTkEntry(frame_limites, width=60)
        entry_vib_limit.insert(0, "1.5")
        entry_vib_limit.pack(pady=(0, 8))
        entry_vib_limit.bind('<KeyRelease>', lambda e: atualizar_estado_iniciar())
    if not grafico_tilt_var.get() and not grafico_vib_var.get():
        label_nenhum = ctk.CTkLabel(frame_limites, text="Nenhum gráfico selecionado", font=('Segoe UI', 12, 'italic'), text_color=COR_LARANJA)
        label_nenhum.pack(pady=10)
    atualizar_estado_iniciar()

# Atualizar estado ao mudar checkboxes
grafico_tilt_var.trace_add('write', lambda *a: atualizar_estado_iniciar())
grafico_vib_var.trace_add('write', lambda *a: atualizar_estado_iniciar())

# Remover o botão de relatório do lado esquerdo
# (Remover este bloco)
# btn_report = ctk.CTkButton(
#     btn_frame, text='Relatório',
#     fg_color=COR_LARANJA, hover_color='#FFB266',
#     text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
#     width=140, height=40, corner_radius=10,
#     command=gerar_relatorio, state='disabled'
# )
# btn_report.grid(row=0, column=1, padx=10, pady=10)

# ===== BOTÃO INICIAR NO FINAL DA ESQUERDA =====
btn_start = ctk.CTkButton(
    frame_esquerdo, text='Iniciar',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=lambda: start_recepcao(),
    state='disabled'  # Começa desabilitado
)
btn_start.pack(side='bottom', pady=20)

# Mover a chamada para cá, após btn_start existir
def setup_inputs_iniciais():
    atualizar_inputs_limites()
setup_inputs_iniciais()
# ===== FIM ABA INFERIOR =====

# ===== LADO DIREITO: PASSO A PASSO E GRÁFICOS =====

# Frame para passo a passo
frame_passos = ctk.CTkFrame(frame_direito, fg_color='transparent')
frame_passos.pack(fill='both', expand=True)
label_passos = ctk.CTkLabel(
    frame_passos,
    text=(
        'Como usar o Riggy:\n'
        '1. Selecione os gráficos desejados à esquerda.\n'
        '2. Defina os limites para cada gráfico selecionado.\n'
        '3. Clique em Iniciar para começar a receber dados.\n'
        '4. Clique em Encerrar para parar.\n'
        '5. Gere o relatório após encerrar.'
    ),
    font=('Segoe UI', 15),
    justify='left',
    text_color=COR_TEXTO
)
label_passos.pack(padx=30, pady=30, anchor='center')

# Frame para gráficos e botões
frame_graficos = ctk.CTkFrame(frame_direito, fg_color='transparent')
# Empacotar o canvas uma única vez dentro de frame_graficos
canvas.get_tk_widget().pack(fill='both', expand=True, pady=(0, 10))

# Remover mostrar_canvas, esconder_canvas, canvas_esta_visivel

# Frame dos botões de controle
frame_botoes = ctk.CTkFrame(frame_graficos, fg_color='transparent')
frame_botoes.pack(fill='x', pady=(10, 10))

btn_encerrar = ctk.CTkButton(
    frame_botoes, text='Encerrar',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=lambda: stop_recepcao(),
    state='disabled'
)
btn_encerrar.pack(side='left', padx=10)

btn_report = ctk.CTkButton(
    frame_botoes, text='Gerar relatório',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=gerar_relatorio, state='disabled'
)
btn_report.pack(side='left', padx=10)

# Função para alternar conteúdo do lado direito
# (Apenas pack/pack_forget do frame_graficos, não do canvas)
def atualizar_lado_direito(estado):
    # estado: 'passos', 'graficos', 'encerrado'
    if estado == 'passos':
        frame_graficos.pack_forget()
        frame_passos.pack(fill='both', expand=True)
    elif estado == 'graficos':
        frame_passos.pack_forget()
        frame_graficos.pack(fill='both', expand=True)
        btn_encerrar.configure(state='normal')
        btn_report.configure(state='disabled')
    elif estado == 'encerrado':
        frame_passos.pack_forget()
        frame_graficos.pack(fill='both', expand=True)
        btn_encerrar.configure(state='disabled')
        btn_report.configure(state='normal')

# Inicialmente mostrar passo a passo
atualizar_lado_direito('passos')

def start_recepcao():
    global running, thread, TILT_THRESHOLD, VIB_THRESHOLD
    reset_dados()
    # LER LIMITES DIGITADOS
    try:
        if grafico_tilt_var.get() and entry_tilt_limit:
            TILT_THRESHOLD = float(entry_tilt_limit.get())
    except:
        TILT_THRESHOLD = 80.0  # valor padrão
    try:
        if grafico_vib_var.get() and entry_vib_limit:
            VIB_THRESHOLD = float(entry_vib_limit.get())
    except:
        VIB_THRESHOLD = 1.5  # valor padrão
    running = True
    status_label.configure(text='Recebendo...', text_color=COR_LARANJA)
    btn_start.configure(state='disabled')
    atualizar_lado_direito('graficos')
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
    btn_start.configure(state='normal')
    atualizar_lado_direito('encerrado')

app.mainloop()
