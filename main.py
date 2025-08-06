import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import socket
import threading
import time
import pygame
import json
from datetime import datetime
import os
from collections import deque
import math
import statistics
import subprocess
import cv2
import numpy as np

# Novas importações para EPUB
from ebooklib import epub
from jinja2 import Template
import base64

# === CONFIGURAÇÕES ===
PORTA_UDP = 5000
TIMEOUT = 0.01
LP_ALPHA = 0.9
WINDOW_SIZE = 20
TARGET_FPS = 15
FRAME_INTERVAL = 1.0 / TARGET_FPS
BUFFER_SIZE = 2048
gravacao_inicio = None
gravacao_fim = None

# === NORMAS TÉCNICAS BRASILEIRAS ===
estruturas_normas = {
    'Concreto Armado (NBR 6118)': {
        'tilt': 1.0,
        'vib': 0.7,
        'norma': 'NBR 6118',
        'descricao': 'Estruturas de concreto armado - Procedimento'
    },
    'Estruturas de Aço (NBR 8800)': {
        'tilt': 1.5,
        'vib': 0.5,
        'norma': 'NBR 8800',
        'descricao': 'Projeto de estruturas de aço e de estruturas mistas de aço e concreto'
    },
    'Estruturas Leves (NBR 15370)': {
        'tilt': 2.0,
        'vib': 0.3,
        'norma': 'NBR 15370',
        'descricao': 'Estruturas de madeira - Métodos de ensaio'
    },
    'Pontes e Viadutos (NBR 7188)': {
        'tilt': 0.8,
        'vib': 0.4,
        'norma': 'NBR 7188',
        'descricao': 'Carga móvel rodoviária e de pedestres em pontes'
    },
    'Estruturas Pré-moldadas (NBR 9062)': {
        'tilt': 1.2,
        'vib': 0.6,
        'norma': 'NBR 9062',
        'descricao': 'Projeto e execução de estruturas de concreto pré-moldado'
    },
    'Personalizada': {
        'tilt': 80.0,
        'vib': 1.5,
        'norma': 'Limites Personalizados',
        'descricao': 'Limites definidos pelo usuário'
    }
}

# Variáveis globais para limites atuais
TILT_THRESHOLD = 80.0
VIB_THRESHOLD = 1.5
ESTRUTURA_ATUAL = 'Personalizada'
UNIDADE_VIB_ATUAL = 'g'

# === ÁUDIO ===
pygame.mixer.init()
def tocar_alerta(nome_arquivo):
    if os.path.isfile(nome_arquivo):
        pygame.mixer.music.load(nome_arquivo)
        pygame.mixer.music.play()

# === VARIÁVEIS GLOBAIS ===
running = False
thread = None
recording = False
video_writer = None
video_filename = None
frames_buffer = []
last_frame_time = 0

data_thread = None
graph_thread = None
video_thread = None

import queue
data_queue = queue.Queue()
graph_queue = queue.Queue()

graph_cache = {}
last_update_time = 0
UPDATE_INTERVAL = 0.1

performance_stats = {
    'frames_capturados': 0,
    'tempo_ultima_atualizacao': 0,
    'fps_real': 0
}

loading_dots = 0
loading_timer = None

INTERPOLACAO_HABILITADA = False
encerrado = False

tempo = []
tilts = deque(maxlen=WINDOW_SIZE)
vibracoes = deque(maxlen=WINDOW_SIZE)
alerts = []

tilts_all = []
vibracoes_all = []

tilt_alerted = False
vib_alerted = False
t = 0
gravity = [0.0, 0.0, 9.81]

# === FUNÇÕES DE CONVERSÃO DE UNIDADES ===
def g_para_ms2(valor_g):
    """Converte aceleração de g para m/s²"""
    return valor_g * 9.81

def ms2_para_g(valor_ms2):
    """Converte aceleração de m/s² para g"""
    return valor_ms2 / 9.81

def obter_limite_vib_convertido():
    """Obtém o limite de vibração na unidade correta"""
    global VIB_THRESHOLD, UNIDADE_VIB_ATUAL
    if UNIDADE_VIB_ATUAL == 'm/s²':
        return VIB_THRESHOLD
    else:
        return VIB_THRESHOLD

def converter_vibracao_para_unidade_norma(vib_g):
    """Converte vibração de g para a unidade da norma (m/s²)"""
    global UNIDADE_VIB_ATUAL
    if UNIDADE_VIB_ATUAL == 'm/s²':
        return g_para_ms2(vib_g)
    else:
        return vib_g

# === GRAVAÇÃO DE VÍDEO ===
def iniciar_gravacao():
    global recording, video_writer, video_filename, frames_buffer, gravacao_inicio
    if recording:
        return
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = f"gravacao_graficos_{now}.mp4"
    recording = True
    frames_buffer = []
    gravacao_inicio = datetime.now()
    print(f"Iniciando gravação: {video_filename}")

def finalizar_gravacao():
    global recording, video_writer, frames_buffer, gravacao_fim
    if not recording:
        return
    recording = False
    gravacao_fim = datetime.now()

    if len(frames_buffer) == 0:
        print("Nenhum frame capturado para gravação")
        return
    try:
        height, width, channels = frames_buffer[0].shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        duracao_segundos = (gravacao_fim - gravacao_inicio).total_seconds()
        fps_real = len(frames_buffer) / duracao_segundos if duracao_segundos > 0 else TARGET_FPS
        
        fps_video = fps_real
        video_writer = cv2.VideoWriter(video_filename, fourcc, fps_video, (width, height))
        
        if len(frames_buffer) > 1:
            print(f"Usando frames reais: {len(frames_buffer)} frames")
            print(f"FPS real calculado: {fps_video:.2f}")
            print(f"Velocidade do vídeo será igual à velocidade real do teste")
        
        for frame in frames_buffer:
            video_writer.write(frame)
        video_writer.release()
        video_writer = None
        
        duracao_real = (gravacao_fim - gravacao_inicio).total_seconds()
        fps_real = len(frames_buffer) / duracao_real if duracao_real > 0 else 0
        performance_stats['fps_real'] = fps_real
        
        print(f"Gravação finalizada: {video_filename}")
        print(f"Frames capturados: {len(frames_buffer)}")
        print(f"FPS real: {fps_video:.2f}")
        print(f"Duração do teste: {duracao_segundos:.2f} segundos")
        print(f"Duração do vídeo: {len(frames_buffer) / fps_video:.2f} segundos")
        print(f"✅ Vídeo com velocidade correta!")
        if video_filename and os.path.isfile(video_filename):
            print(f"Vídeo salvo: {video_filename}")
    except Exception as e:
        print(f"Erro ao finalizar gravação: {e}")
        if video_writer:
            video_writer.release()

def capturar_frame_grafico():
    global frames_buffer, last_frame_time, performance_stats
    if not recording:
        return
    
    current_time = time.time()
    if current_time - last_frame_time < FRAME_INTERVAL:
        return
    
    last_frame_time = current_time
    
    performance_stats['frames_capturados'] += 1
    performance_stats['tempo_ultima_atualizacao'] = current_time
    
    try:
        canvas.draw()
        canvas.flush_events()
        
        buf = canvas.buffer_rgba()
        buf = np.asarray(buf)
        buf = buf.reshape(canvas.get_width_height()[::-1] + (4,))
        
        frame_rgb = buf[:, :, :3]
        frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        frame = cv2.resize(frame, (640, 480))
        frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
        
        frames_buffer.append(frame.copy())
        
        if len(frames_buffer) > 1000:
            frames_buffer.pop(0)
            
    except Exception as e:
        print(f"Erro ao capturar frame: {e}")
        try:
            buf = np.frombuffer(canvas.tostring_rgb(), dtype=np.uint8)
            buf = buf.reshape(canvas.get_width_height()[::-1] + (3,))
            frame = cv2.cvtColor(buf, cv2.COLOR_RGB2BGR)
            frame = cv2.resize(frame, (640, 480))
            frames_buffer.append(frame.copy())
            if len(frames_buffer) > 500:
                frames_buffer.pop(0)
        except Exception as e2:
            print(f"Erro no fallback: {e2}")

# === TEMPLATE HTML PARA EPUB ===
EPUB_TEMPLATE = """
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{{ titulo }}</title>
    <meta charset="utf-8"/>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 20px;
            color: #333;
        }
        .header {
            text-align: center;
            border-bottom: 3px solid #FF8800;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .logo {
            color: #FF8800;
            font-size: 24px;
            font-weight: bold;
        }
        .subtitle {
            color: #666;
            font-size: 14px;
        }
        .section {
            margin: 20px 0;
            padding: 15px;
            border-left: 4px solid #FF8800;
            background-color: #f9f9f9;
        }
        .section-title {
            color: #FF8800;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .norma-section {
            background-color: #f0f0ff;
            border: 2px solid #0066cc;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 15px 0;
        }
        .stat-item {
            margin: 5px 0;
        }
        .status-conforme {
            color: #008000;
            font-weight: bold;
        }
        .status-nao-conforme {
            color: #cc0000;
            font-weight: bold;
        }
        .video-section {
            background-color: #1a1a1a;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            text-align: center;
        }
        .video-container {
            margin: 20px 0;
        }
        video {
            max-width: 100%;
            height: auto;
            border-radius: 5px;
        }
        .footer {
            border-top: 1px solid #FF8800;
            padding-top: 15px;
            margin-top: 30px;
            font-size: 12px;
            color: #666;
        }
        .chart-container {
            text-align: center;
            margin: 20px 0;
        }
        .chart-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">RELATÓRIO RIGGY</div>
        <div class="subtitle">UDP SensaGram - Monitoramento de Sensores</div>
    </div>

    <div class="norma-section">
        <div class="section-title">📋 NORMA TÉCNICA APLICADA</div>
        <p><strong>Estrutura Avaliada:</strong> {{ estrutura_atual }}</p>
        <p><strong>Norma Aplicada:</strong> {{ norma_info.norma }}</p>
        <p><strong>Descrição:</strong> {{ norma_info.descricao }}</p>
        <p><strong>Limites:</strong> Inclinação ≤ {{ limite_tilt }}° | Vibração ≤ {{ limite_vib }} {{ unidade_display }}</p>
    </div>

    <div class="section">
        <div class="section-title">INFORMAÇÕES GERAIS</div>
        <div class="stats-grid">
            <div>
                <div class="stat-item"><strong>Data e Hora:</strong> {{ data_hora }}</div>
                <div class="stat-item"><strong>Pontos Coletados:</strong> {{ pontos_coletados }}</div>
                <div class="stat-item"><strong>Duração do Teste:</strong> {{ duracao_teste }} segundos</div>
            </div>
            <div>
                <div class="stat-item"><strong>Alertas de Inclinação:</strong> {{ alertas_tilt }}</div>
                <div class="stat-item"><strong>Alertas de Vibração:</strong> {{ alertas_vib }}</div>
            </div>
        </div>
    </div>

    {% if mostrar_tilt %}
    <div class="section">
        <div class="section-title">📐 ESTATÍSTICAS DE INCLINAÇÃO (°)</div>
        <div class="stats-grid">
            <div>
                <div class="stat-item"><strong>Média:</strong> {{ tilt_media }}°</div>
                <div class="stat-item"><strong>Máximo:</strong> {{ tilt_max }}°</div>
                <div class="stat-item"><strong>Mínimo:</strong> {{ tilt_min }}°</div>
            </div>
            <div>
                <div class="stat-item"><strong>Desvio Padrão:</strong> {{ tilt_std }}°</div>
                <div class="stat-item"><strong>Limite da Norma:</strong> {{ limite_tilt }}°</div>
                <div class="stat-item"><strong>Status:</strong> 
                    <span class="{{ 'status-conforme' if tilt_status == 'CONFORME' else 'status-nao-conforme' }}">
                        {{ tilt_status }}
                    </span>
                </div>
                <div class="stat-item"><strong>Avaliação:</strong> {{ tilt_avaliacao }}</div>
            </div>
        </div>
    </div>
    {% endif %}

    {% if mostrar_vib %}
    <div class="section">
        <div class="section-title">📳 ESTATÍSTICAS DE VIBRAÇÃO ({{ unidade_display }})</div>
        <div class="stats-grid">
            <div>
                <div class="stat-item"><strong>Média:</strong> {{ vib_media }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Máximo:</strong> {{ vib_max }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Mínimo:</strong> {{ vib_min }}{{ unidade_display }}</div>
            </div>
            <div>
                <div class="stat-item"><strong>Desvio Padrão:</strong> {{ vib_std }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Limite da Norma:</strong> {{ limite_vib }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Status:</strong> 
                    <span class="{{ 'status-conforme' if vib_status == 'CONFORME' else 'status-nao-conforme' }}">
                        {{ vib_status }}
                    </span>
                </div>
                <div class="stat-item"><strong>Avaliação:</strong> {{ vib_avaliacao }}</div>
            </div>
        </div>
        {% if unidade_display == 'm/s²' %}
        <p style="font-size: 12px; color: #666; margin-top: 10px;">
            * Valores convertidos de g para m/s² conforme NBR ISO 2631-1
        </p>
        {% endif %}
    </div>
    {% endif %}

    {% if graficos %}
    <div class="section">
        <div class="section-title">📊 GRÁFICOS COMPLETOS POR TEMPO</div>
        {% for grafico in graficos %}
        <div class="chart-container">
            <img src="{{ grafico.src }}" alt="{{ grafico.alt }}" />
            <p>{{ grafico.titulo }}</p>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    {% if video_data %}
    <div class="video-section">
        <div class="section-title" style="color: #FF8800;">🎥 GRAVAÇÃO DOS GRÁFICOS</div>
        <p><strong>Arquivo:</strong> {{ video_filename }}</p>
        <p><strong>Frames Capturados:</strong> {{ frames_capturados }}</p>
        <p><strong>Duração Aproximada:</strong> {{ duracao_video }} segundos</p>
        
        <div class="video-container">
            <video controls>
                <source src="{{ video_src }}" type="video/mp4">
                Seu leitor de EPUB não suporta vídeos HTML5.
            </video>
        </div>
        
        <p style="color: #FFB266;">📎 Vídeo embutido no EPUB</p>
        <p style="color: #ccc; font-size: 12px;">
            O vídeo está incorporado diretamente no arquivo EPUB e pode ser reproduzido 
            em leitores compatíveis com HTML5 e vídeo.
        </p>
    </div>
    {% endif %}

    <div class="footer">
        <p><strong>Gerado por Riggy - UDP SensaGram</strong></p>
        <p>Relatório gerado em {{ data_hora }}</p>
    </div>
</body>
</html>
"""

# === GERAÇÃO DE RELATÓRIO EPUB ===
def gerar_relatorio_epub():
    global video_filename, gravacao_inicio, gravacao_fim, ESTRUTURA_ATUAL, UNIDADE_VIB_ATUAL
    
    # Desabilita o botão e mostra loading
    btn_report.configure(state='disabled', text='Gerando relatório EPUB...')
    app.update()

    finalizar_gravacao()

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    epub_filename = f"relatorio_{now}.epub"

    # Calcula estatísticas (mantém o código existente)
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

    # Converte estatísticas de vibração para a unidade da norma se necessário
    if UNIDADE_VIB_ATUAL == 'm/s²':
        vib_media_norma = g_para_ms2(vib_media)
        vib_max_norma = g_para_ms2(vib_max)
        vib_min_norma = g_para_ms2(vib_min)
        vib_std_norma = g_para_ms2(vib_std)
        unidade_display = 'm/s²'
    else:
        vib_media_norma = vib_media
        vib_max_norma = vib_max
        vib_min_norma = vib_min
        vib_std_norma = vib_std
        unidade_display = 'g'

    duracao_real = (gravacao_fim - gravacao_inicio).total_seconds() if gravacao_inicio and gravacao_fim else len(frames_buffer)/10

    # Prepara dados para o template
    norma_info = estruturas_normas.get(ESTRUTURA_ATUAL, estruturas_normas['Personalizada'])
    
    # Status de conformidade
    tilt_status = "CONFORME" if tilt_max < TILT_THRESHOLD else "NÃO CONFORME"
    vib_max_comparacao = vib_max if UNIDADE_VIB_ATUAL == 'g' else g_para_ms2(vib_max)
    vib_status = "CONFORME" if vib_max_comparacao < VIB_THRESHOLD else "NÃO CONFORME"
    
    # Avaliações técnicas
    if tilt_max < TILT_THRESHOLD * 0.5:
        tilt_avaliacao = "EXCELENTE"
    elif tilt_max < TILT_THRESHOLD * 0.8:
        tilt_avaliacao = "BOM"
    elif tilt_max < TILT_THRESHOLD:
        tilt_avaliacao = "ACEITÁVEL"
    else:
        tilt_avaliacao = "CRÍTICO"
    
    if vib_max_comparacao < VIB_THRESHOLD * 0.5:
        vib_avaliacao = "EXCELENTE"
    elif vib_max_comparacao < VIB_THRESHOLD * 0.8:
        vib_avaliacao = "BOM"
    elif vib_max_comparacao < VIB_THRESHOLD:
        vib_avaliacao = "ACEITÁVEL"
    else:
        vib_avaliacao = "CRÍTICO"

    # Gera gráficos para o EPUB
    graficos_info = []
    graficos_paths = salvar_graficos_completos_para_epub(tilts_all, vibracoes_all, grafico_tilt_var.get(), grafico_vib_var.get())
    
    for i, path in enumerate(graficos_paths):
        if 'tilt' in path:
            graficos_info.append({
                'src': f'images/grafico_tilt_{i}.png',
                'alt': 'Gráfico de Inclinação por Tempo',
                'titulo': 'Inclinação (°) por Tempo',
                'path': path
            })
        else:
            graficos_info.append({
                'src': f'images/grafico_vib_{i}.png',
                'alt': 'Gráfico de Vibração por Tempo',
                'titulo': f'Vibração ({unidade_display}) por Tempo',
                'path': path
            })

    # === NOVA LÓGICA PARA VÍDEO ===
    video_base64 = None
    video_size_mb = 0
    if video_filename and os.path.isfile(video_filename):
        try:
            # Converte vídeo para H.264 (mais compatível)
            video_h264_filename = f"video_h264_{now}.mp4"
            converter_video_para_h264(video_filename, video_h264_filename)
            
            # Lê o vídeo convertido
            with open(video_h264_filename, 'rb') as video_file:
                video_data = video_file.read()
                video_size_mb = len(video_data) / (1024 * 1024)  # Tamanho em MB
                
                # Se o vídeo for menor que 10MB, converte para base64
                if video_size_mb < 10:
                    video_base64 = base64.b64encode(video_data).decode('utf-8')
                    print(f"✅ Vídeo convertido para base64: {video_size_mb:.2f} MB")
                else:
                    print(f"⚠️ Vídeo muito grande ({video_size_mb:.2f} MB), será anexado como arquivo")
            
            # Remove o arquivo temporário H.264
            if os.path.exists(video_h264_filename):
                os.remove(video_h264_filename)
                
        except Exception as e:
            print(f"Erro ao processar vídeo: {e}")
            # Fallback: usa o vídeo original
            try:
                with open(video_filename, 'rb') as video_file:
                    video_data = video_file.read()
                    video_size_mb = len(video_data) / (1024 * 1024)
            except:
                video_data = None

    # Dados do template
    template_data = {
        'titulo': 'Relatório Riggy - UDP SensaGram',
        'estrutura_atual': ESTRUTURA_ATUAL,
        'norma_info': norma_info,
        'limite_tilt': f"{TILT_THRESHOLD:.1f}",
        'limite_vib': f"{VIB_THRESHOLD:.2f}",
        'unidade_display': unidade_display,
        'data_hora': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        'pontos_coletados': len(tempo),
        'duracao_teste': f"{duracao_real:.1f}",
        'alertas_tilt': sum(1 for a in alerts if a[0]=='tilt') if grafico_tilt_var.get() else 0,
        'alertas_vib': sum(1 for a in alerts if a[0]=='vibração') if grafico_vib_var.get() else 0,
        'mostrar_tilt': grafico_tilt_var.get(),
        'mostrar_vib': grafico_vib_var.get(),
        'tilt_media': f"{tilt_media:.2f}",
        'tilt_max': f"{tilt_max:.2f}",
        'tilt_min': f"{tilt_min:.2f}",
        'tilt_std': f"{tilt_std:.2f}",
        'tilt_status': tilt_status,
        'tilt_avaliacao': tilt_avaliacao,
        'vib_media': f"{vib_media_norma:.3f}",
        'vib_max': f"{vib_max_norma:.3f}",
        'vib_min': f"{vib_min_norma:.3f}",
        'vib_std': f"{vib_std_norma:.3f}",
        'vib_status': vib_status,
        'vib_avaliacao': vib_avaliacao,
        'graficos': graficos_info,
        'video_data': video_filename and os.path.isfile(video_filename),
        'video_filename': os.path.basename(video_filename) if video_filename else '',
        'frames_capturados': len(frames_buffer),
        'duracao_video': f"{duracao_real:.1f}",
        'video_src': 'video/gravacao.mp4' if video_filename else '',
        'video_base64': video_base64,
        'video_size_mb': f"{video_size_mb:.2f}"
    }

    # Cria o EPUB
    try:
        book = epub.EpubBook()
        
        # Metadados
        book.set_identifier('riggy-report-' + now)
        book.set_title('Relatório Riggy - UDP SensaGram')
        book.set_language('pt-BR')
        book.add_author('Riggy - UDP SensaGram')
        book.add_metadata('DC', 'description', 'Relatório de monitoramento de sensores estruturais')

        # Renderiza o template HTML
        template = Template(EPUB_TEMPLATE_MELHORADO)
        html_content = template.render(**template_data)
        
        # Cria o capítulo principal
        chapter = epub.EpubHtml(title='Relatório de Monitoramento', 
                              file_name='relatorio.xhtml', 
                              lang='pt-BR')
        chapter.content = html_content
        book.add_item(chapter)

        # Adiciona imagens dos gráficos
        for grafico in graficos_info:
            if os.path.exists(grafico['path']):
                with open(grafico['path'], 'rb') as img_file:
                    img_data = img_file.read()
                
                img_item = epub.EpubItem(
                    uid=f"img_{grafico['src'].split('/')[-1]}",
                    file_name=grafico['src'],
                    media_type="image/png",
                    content=img_data
                )
                book.add_item(img_item)

        # Adiciona o vídeo se não foi convertido para base64
        if video_filename and os.path.isfile(video_filename) and not video_base64:
            try:
                with open(video_filename, 'rb') as video_file:
                    video_data = video_file.read()
                
                video_item = epub.EpubItem(
                    uid="video_gravacao",
                    file_name="video/gravacao.mp4",
                    media_type="video/mp4",
                    content=video_data
                )
                book.add_item(video_item)
                print(f"✅ Vídeo anexado ao EPUB: {len(video_data)} bytes")
            except Exception as e:
                print(f"Erro ao anexar vídeo ao EPUB: {e}")

        # Define a ordem de leitura
        book.toc = [chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Define a spine (ordem dos capítulos)
        book.spine = ['nav', chapter]

        # Salva o EPUB
        epub.write_epub(epub_filename, book, {})
        
        # Remove arquivos temporários dos gráficos
        for path in graficos_paths:
            try:
                os.remove(path)
            except Exception as e:
                print(f"Erro ao remover arquivo temporário {path}: {e}")

        print(f"✅ Relatório EPUB gerado: {epub_filename}")
        if video_base64:
            print(f"✅ Vídeo embutido como base64 no HTML")
        elif video_filename and os.path.isfile(video_filename):
            print(f"✅ Vídeo anexado como arquivo separado")
        
        # Tenta abrir o arquivo
        try:
            os.startfile(epub_filename)
        except:
            print(f"Arquivo salvo em: {os.path.abspath(epub_filename)}")

    except Exception as e:
        print(f"Erro ao gerar EPUB: {e}")
        import traceback
        traceback.print_exc()
    
    # Para a animação e restaura o botão
    global loading_timer
    if loading_timer:
        app.after_cancel(loading_timer)
    btn_report.configure(state='normal', text='Gerar relatório EPUB')
    app.update()

def converter_video_para_h264(input_file, output_file):
    """Converte vídeo para H.264 usando OpenCV para melhor compatibilidade"""
    try:
        cap = cv2.VideoCapture(input_file)
        
        # Propriedades do vídeo original
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Codec H.264 (mais compatível)
        fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264
        out = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
        
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
            frame_count += 1
        
        cap.release()
        out.release()
        
        print(f"✅ Vídeo convertido para H.264: {frame_count} frames")
        return True
        
    except Exception as e:
        print(f"Erro na conversão H.264: {e}")
        return False

# === TEMPLATE HTML MELHORADO PARA EPUB ===
EPUB_TEMPLATE_MELHORADO = """
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{{ titulo }}</title>
    <meta charset="utf-8"/>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 20px;
            color: #333;
        }
        .header {
            text-align: center;
            border-bottom: 3px solid #FF8800;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .logo {
            color: #FF8800;
            font-size: 24px;
            font-weight: bold;
        }
        .subtitle {
            color: #666;
            font-size: 14px;
        }
        .section {
            margin: 20px 0;
            padding: 15px;
            border-left: 4px solid #FF8800;
            background-color: #f9f9f9;
        }
        .section-title {
            color: #FF8800;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .norma-section {
            background-color: #f0f0ff;
            border: 2px solid #0066cc;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 15px 0;
        }
        .stat-item {
            margin: 5px 0;
        }
        .status-conforme {
            color: #008000;
            font-weight: bold;
        }
        .status-nao-conforme {
            color: #cc0000;
            font-weight: bold;
        }
        .video-section {
            background-color: #1a1a1a;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            text-align: center;
        }
        .video-container {
            margin: 20px 0;
            background-color: #000;
            border-radius: 5px;
            padding: 10px;
        }
        video {
            max-width: 100%;
            height: auto;
            border-radius: 5px;
            background-color: #000;
        }
        .video-fallback {
            background-color: #333;
            padding: 20px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .video-fallback a {
            color: #FF8800;
            text-decoration: none;
            font-weight: bold;
        }
        .video-fallback a:hover {
            text-decoration: underline;
        }
        .footer {
            border-top: 1px solid #FF8800;
            padding-top: 15px;
            margin-top: 30px;
            font-size: 12px;
            color: #666;
        }
        .chart-container {
            text-align: center;
            margin: 20px 0;
        }
        .chart-container img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .video-info {
            font-size: 12px;
            color: #ccc;
            margin: 10px 0;
        }
        .compatibility-note {
            background-color: #2a2a2a;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
            font-size: 12px;
            color: #aaa;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">RELATÓRIO RIGGY</div>
        <div class="subtitle">UDP SensaGram - Monitoramento de Sensores</div>
    </div>

    <div class="norma-section">
        <div class="section-title">📋 NORMA TÉCNICA APLICADA</div>
        <p><strong>Estrutura Avaliada:</strong> {{ estrutura_atual }}</p>
        <p><strong>Norma Aplicada:</strong> {{ norma_info.norma }}</p>
        <p><strong>Descrição:</strong> {{ norma_info.descricao }}</p>
        <p><strong>Limites:</strong> Inclinação ≤ {{ limite_tilt }}° | Vibração ≤ {{ limite_vib }} {{ unidade_display }}</p>
    </div>

    <div class="section">
        <div class="section-title">INFORMAÇÕES GERAIS</div>
        <div class="stats-grid">
            <div>
                <div class="stat-item"><strong>Data e Hora:</strong> {{ data_hora }}</div>
                <div class="stat-item"><strong>Pontos Coletados:</strong> {{ pontos_coletados }}</div>
                <div class="stat-item"><strong>Duração do Teste:</strong> {{ duracao_teste }} segundos</div>
            </div>
            <div>
                <div class="stat-item"><strong>Alertas de Inclinação:</strong> {{ alertas_tilt }}</div>
                <div class="stat-item"><strong>Alertas de Vibração:</strong> {{ alertas_vib }}</div>
            </div>
        </div>
    </div>

    {% if mostrar_tilt %}
    <div class="section">
        <div class="section-title">📐 ESTATÍSTICAS DE INCLINAÇÃO (°)</div>
        <div class="stats-grid">
            <div>
                <div class="stat-item"><strong>Média:</strong> {{ tilt_media }}°</div>
                <div class="stat-item"><strong>Máximo:</strong> {{ tilt_max }}°</div>
                <div class="stat-item"><strong>Mínimo:</strong> {{ tilt_min }}°</div>
            </div>
            <div>
                <div class="stat-item"><strong>Desvio Padrão:</strong> {{ tilt_std }}°</div>
                <div class="stat-item"><strong>Limite da Norma:</strong> {{ limite_tilt }}°</div>
                <div class="stat-item"><strong>Status:</strong> 
                    <span class="{{ 'status-conforme' if tilt_status == 'CONFORME' else 'status-nao-conforme' }}">
                        {{ tilt_status }}
                    </span>
                </div>
                <div class="stat-item"><strong>Avaliação:</strong> {{ tilt_avaliacao }}</div>
            </div>
        </div>
    </div>
    {% endif %}

    {% if mostrar_vib %}
    <div class="section">
        <div class="section-title">📳 ESTATÍSTICAS DE VIBRAÇÃO ({{ unidade_display }})</div>
        <div class="stats-grid">
            <div>
                <div class="stat-item"><strong>Média:</strong> {{ vib_media }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Máximo:</strong> {{ vib_max }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Mínimo:</strong> {{ vib_min }}{{ unidade_display }}</div>
            </div>
            <div>
                <div class="stat-item"><strong>Desvio Padrão:</strong> {{ vib_std }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Limite da Norma:</strong> {{ limite_vib }}{{ unidade_display }}</div>
                <div class="stat-item"><strong>Status:</strong> 
                    <span class="{{ 'status-conforme' if vib_status == 'CONFORME' else 'status-nao-conforme' }}">
                        {{ vib_status }}
                    </span>
                </div>
                <div class="stat-item"><strong>Avaliação:</strong> {{ vib_avaliacao }}</div>
            </div>
        </div>
        {% if unidade_display == 'm/s²' %}
        <p style="font-size: 12px; color: #666; margin-top: 10px;">
            * Valores convertidos de g para m/s² conforme NBR ISO 2631-1
        </p>
        {% endif %}
    </div>
    {% endif %}

    {% if graficos %}
    <div class="section">
        <div class="section-title">📊 GRÁFICOS COMPLETOS POR TEMPO</div>
        {% for grafico in graficos %}
        <div class="chart-container">
            <img src="{{ grafico.src }}" alt="{{ grafico.alt }}" />
            <p>{{ grafico.titulo }}</p>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    {% if video_data %}
    <div class="video-section">
        <div class="section-title" style="color: #FF8800;">🎥 GRAVAÇÃO DOS GRÁFICOS</div>
        <p><strong>Arquivo:</strong> {{ video_filename }}</p>
        <p><strong>Frames Capturados:</strong> {{ frames_capturados }}</p>
        <p><strong>Duração:</strong> {{ duracao_video }} segundos</p>
        <p><strong>Tamanho:</strong> {{ video_size_mb }} MB</p>
        
        <div class="video-container">
            {% if video_base64 %}
            <!-- Vídeo embutido como base64 -->
            <video controls preload="metadata" style="width: 100%; max-width: 640px;">
                <source src="data:video/mp4;base64,{{ video_base64 }}" type="video/mp4">
                <p style="color: #ff6666;">Seu leitor de EPUB não suporta vídeos HTML5.</p>
            </video>
            <div class="video-info">
                ✅ Vídeo embutido diretamente no EPUB (base64)
            </div>
            {% else %}
            <!-- Vídeo como arquivo anexo -->
            <video controls preload="metadata" style="width: 100%; max-width: 640px;">
                <source src="{{ video_src }}" type="video/mp4">
                <div class="video-fallback">
                    <p style="color: #ff6666;">❌ Não foi possível carregar o vídeo</p>
                    <p>O vídeo está anexado ao EPUB como arquivo separado.</p>
                    <p>Tente extrair o arquivo "{{ video_filename }}" do EPUB.</p>
                </div>
            </video>
            <div class="video-info">
                📎 Vídeo anexado como arquivo separado
            </div>
            {% endif %}
        </div>
        
        <div class="compatibility-note">
            <strong>💡 Dica de Compatibilidade:</strong><br>
            • <strong>Calibre:</strong> Suporta vídeos HTML5 ✅<br>
            • <strong>Adobe Digital Editions:</strong> Suporte limitado ⚠️<br>
            • <strong>Apple Books:</strong> Suporta vídeos ✅<br>
            • <strong>Google Play Books:</strong> Suporte limitado ⚠️<br>
            <br>
            Se o vídeo não reproduzir, o arquivo original está salvo em: <strong>{{ video_filename }}</strong>
        </div>
    </div>
    {% endif %}

    <div class="footer">
        <p><strong>Gerado por Riggy - UDP SensaGram</strong></p>
        <p>Relatório gerado em {{ data_hora }}</p>
    </div>
</body>
</html>
"""

def salvar_graficos_completos_para_epub(tilts_all, vibracoes_all, show_tilt, show_vib):
    """Salva gráficos como imagens PNG para o EPUB"""
    global UNIDADE_VIB_ATUAL
    paths = []
    
    if show_tilt and tilts_all:
        fig_tilt, ax_tilt = plt.subplots(figsize=(8, 4))
        ax_tilt.plot(list(range(len(tilts_all))), tilts_all, color='#FF8800', linewidth=2)
        ax_tilt.set_ylim(0, 100)
        ax_tilt.set_title('Inclinação (°) por tempo', fontsize=14, fontweight='bold')
        ax_tilt.set_ylabel('Grau')
        ax_tilt.set_xlabel('Tempo (amostras)')
        ax_tilt.grid(True, alpha=0.3)
        fig_tilt.tight_layout()
        tilt_path = f"tilt_grafico_epub_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fig_tilt.savefig(tilt_path, dpi=150, bbox_inches='tight')
        plt.close(fig_tilt)
        paths.append(tilt_path)
    
    if show_vib and vibracoes_all:
        fig_vib, ax_vib = plt.subplots(figsize=(8, 4))
        
        # Converte dados para a unidade correta se necessário
        vib_data = vibracoes_all
        unidade_display = 'g'
        if UNIDADE_VIB_ATUAL == 'm/s²':
            vib_data = [g_para_ms2(v) for v in vibracoes_all]
            unidade_display = 'm/s²'
            
        ax_vib.plot(list(range(len(vib_data))), vib_data, color='#FFB266', linewidth=2)
        
        # Ajusta escala baseada na unidade
        if UNIDADE_VIB_ATUAL == 'm/s²':
            ax_vib.set_ylim(0, 50)
        else:
            ax_vib.set_ylim(0, 5)
            
        ax_vib.set_title(f'Vibração ({unidade_display}) por tempo', fontsize=14, fontweight='bold')
        ax_vib.set_ylabel(unidade_display)
        ax_vib.set_xlabel('Tempo (amostras)')
        ax_vib.grid(True, alpha=0.3)
        fig_vib.tight_layout()
        vib_path = f"vib_grafico_epub_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fig_vib.savefig(vib_path, dpi=150, bbox_inches='tight')
        plt.close(fig_vib)
        paths.append(vib_path)
    
    return paths

def animar_loading():
    """Anima o texto de loading com pontos"""
    global loading_dots, loading_timer
    loading_dots = (loading_dots + 1) % 4
    dots = "." * loading_dots
    btn_report.configure(text=f'Gerando relatório EPUB{dots}')
    
    if btn_report.cget('state') == 'disabled':
        loading_timer = app.after(500, animar_loading)

def gerar_relatorio_com_loading():
    """Wrapper para gerar relatório com tratamento de erro"""
    global loading_timer
    
    # Inicia animação de loading
    loading_dots = 0
    animar_loading()
    
    try:
        gerar_relatorio_epub()  # Chama a nova função EPUB
    except Exception as e:
        print(f"Erro ao gerar relatório EPUB: {e}")
        if loading_timer:
            app.after_cancel(loading_timer)
        btn_report.configure(state='normal', text='Gerar relatório EPUB')
        app.update()

# === THREAD UDP ===
def processar_dados_thread():
    """Thread separada para processamento de dados UDP"""
    global t, running, gravity, tilt_alerted, vib_alerted
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORTA_UDP))
    sock.settimeout(TIMEOUT)
    
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Calibração da gravidade
    for _ in range(WINDOW_SIZE):
        if not running: return
        try:
            data, _ = sock.recvfrom(BUFFER_SIZE)
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
            data, _ = sock.recvfrom(BUFFER_SIZE)
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

        # Vibração - mantém em g para processamento interno
        total_acc = math.sqrt(ax*ax + ay*ay + az*az)
        vib = abs(total_acc - 9.81)
        vibracoes.append(vib)
        vibracoes_all.append(vib)
        avg_vib = sum(vibracoes) / len(vibracoes) if vibracoes else 0

        tempo.append(t)
        t += 1

        # Alerta de inclinação
        if grafico_tilt_var.get():
            avg_tilt = sum(tilts) / len(tilts) if tilts else 0
            if avg_tilt >= TILT_THRESHOLD and not tilt_alerted:
                alerts.append(('tilt', datetime.now(), avg_tilt))
                tocar_alerta('alerta_inclinacao.mp3')
                tilt_alerted = True
            if avg_tilt < TILT_THRESHOLD - 20:
                tilt_alerted = False

        # Alerta de vibração - compara na unidade correta
        if grafico_vib_var.get():
            if UNIDADE_VIB_ATUAL == 'm/s²':
                avg_vib_comparacao = g_para_ms2(avg_vib)
            else:
                avg_vib_comparacao = avg_vib
                
            if avg_vib_comparacao >= VIB_THRESHOLD and not vib_alerted:
                alerts.append(('vibração', datetime.now(), avg_vib_comparacao))
                tocar_alerta('alerta_vibracao.mp3')
                vib_alerted = True
            if avg_vib_comparacao < VIB_THRESHOLD - (0.3 if UNIDADE_VIB_ATUAL == 'g' else 3.0):
                vib_alerted = False

# === INTERFACE ===
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')

# Cores customizadas
COR_LARANJA = '#FF8800'
COR_PRETO = '#181818'
COR_CINZA = '#232323'
COR_TEXTO = '#FFFFFF'

app = ctk.CTk()
app.title('Riggy - UDP SensaGram (EPUB)')
app.geometry('900x750')
app.configure(bg=COR_PRETO)

# Define o ícone da janela
ico_path = os.path.join(os.path.dirname(__file__), 'riggy-logo.ico')
if os.path.isfile(ico_path):
    try:
        app.iconbitmap(ico_path)
    except Exception:
        pass

# Função para obter o IP local
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
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

# Layout principal
frame_titulo = ctk.CTkFrame(app, fg_color='transparent')
frame_titulo.pack(fill='x', pady=(10, 0))
label_titulo = ctk.CTkLabel(frame_titulo, text='Riggy (EPUB)', font=('Segoe UI', 24, 'bold'), text_color=COR_LARANJA)
label_titulo.pack(anchor='center')

local_ip = get_local_ip()
wifi_ssid = get_wifi_ssid()
label_ip = ctk.CTkLabel(frame_titulo, text=f'ip: {local_ip}  port: {PORTA_UDP}  wifi: {wifi_ssid}', font=('Segoe UI', 14), text_color=COR_TEXTO)
label_ip.pack(anchor='center', pady=(2, 0))

frame_principal = ctk.CTkFrame(app, fg_color='transparent')
frame_principal.pack(fill='both', expand=True, padx=20, pady=10)

frame_esquerdo = ctk.CTkFrame(frame_principal, fg_color=COR_CINZA, corner_radius=16, width=320)
frame_esquerdo.pack(side='left', fill='y', padx=(0, 20), pady=0)
frame_esquerdo.pack_propagate(False)

frame_direito = ctk.CTkFrame(frame_principal, fg_color=COR_CINZA, corner_radius=16)
frame_direito.pack(side='right', fill='both', expand=True, pady=0)

# === SELEÇÃO DE NORMA TÉCNICA ===
frame_norma = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
frame_norma.pack(fill='x', pady=(10, 0), padx=10)

label_norma = ctk.CTkLabel(frame_norma, text="Norma Técnica:", font=('Segoe UI', 14, 'bold'), text_color=COR_LARANJA)
label_norma.pack(pady=(0, 5))

estrutura_var = ctk.StringVar(value='Personalizada')
estrutura_menu = ctk.CTkOptionMenu(
    frame_norma,
    values=list(estruturas_normas.keys()),
    variable=estrutura_var,
    command=lambda _: atualizar_limites_por_norma(),
    font=('Segoe UI', 11),
    width=280
)
estrutura_menu.pack(pady=(0, 10))

label_info_norma = ctk.CTkLabel(frame_norma, text="", font=('Segoe UI', 9), text_color=COR_TEXTO, wraplength=280)
label_info_norma.pack(pady=(0, 10))

# Checkboxes de gráficos
checkbox_frame = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
checkbox_frame.pack(fill='x', pady=(10, 0))

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

status_label = ctk.CTkLabel(frame_esquerdo, text='Pronto para iniciar', font=('Segoe UI', 16, 'bold'), text_color=COR_LARANJA)
status_label.pack(pady=(10, 20))

# Gráficos
fig, axs = plt.subplots(2, 1, figsize=(7, 5))
fig.patch.set_facecolor(COR_CINZA)
fig.tight_layout(pad=3.0)
canvas = FigureCanvasTkAgg(fig, frame_direito)

plt.rcParams['axes.facecolor'] = COR_CINZA
plt.rcParams['figure.facecolor'] = COR_CINZA
plt.rcParams['axes.labelcolor'] = COR_TEXTO
plt.rcParams['xtick.color'] = COR_TEXTO
plt.rcParams['ytick.color'] = COR_TEXTO
plt.rcParams['axes.edgecolor'] = COR_PRETO
plt.rcParams['text.color'] = COR_TEXTO

# Função para suavizar sinal usando FFT (passa-baixa)
def suavizar_fft(sinal, freq_corte=10, fs=50):
    if len(sinal) < 2:
        return sinal
    N = len(sinal)
    y = np.array(sinal)
    y = y - np.mean(y)
    Y = np.fft.fft(y)
    freqs = np.fft.fftfreq(N, d=1/fs)
    Y[np.abs(freqs) > freq_corte] = 0
    y_suave = np.fft.ifft(Y).real + np.mean(sinal)
    return y_suave.tolist()

def update_graph():
    global encerrado, last_update_time, graph_cache, UNIDADE_VIB_ATUAL
    
    current_time = time.time()
    if current_time - last_update_time < UPDATE_INTERVAL:
        if running:
            app.after(50, update_graph)
        return
    
    last_update_time = current_time
    
    for ax in axs:
        ax.clear()
        ax.set_visible(False)

    show_tilt = grafico_tilt_var.get()
    show_vib = grafico_vib_var.get()

    unidade_display = 'm/s²' if UNIDADE_VIB_ATUAL == 'm/s²' else 'g'

    if encerrado:
        if show_tilt:
            axs[0].set_visible(True)
            if tilts_all:
                suave = suavizar_fft(tilts_all)
                axs[0].plot(list(range(len(suave))), suave, color=COR_LARANJA, linewidth=2)
            axs[0].set_ylim(0, 100)
            axs[0].set_title('Inclinação (°) por tempo', color=COR_LARANJA, fontsize=12, fontweight='bold')
            axs[0].set_ylabel('Grau', color=COR_TEXTO)
            axs[0].set_facecolor(COR_CINZA)
        if show_vib:
            idx = 1 if show_tilt else 0
            axs[idx].set_visible(True)
            if vibracoes_all:
                suave = suavizar_fft(vibracoes_all)
                if UNIDADE_VIB_ATUAL == 'm/s²':
                    suave = [g_para_ms2(v) for v in suave]
                axs[idx].plot(list(range(len(suave))), suave, color='#FFB266', linewidth=2)
            
            if UNIDADE_VIB_ATUAL == 'm/s²':
                axs[idx].set_ylim(0, 50)
            else:
                axs[idx].set_ylim(0, 5)
            
            axs[idx].set_title(f'Vibração ({unidade_display}) por tempo', color=COR_LARANJA, fontsize=12, fontweight='bold')
            axs[idx].set_ylabel(unidade_display, color=COR_TEXTO)
            axs[idx].set_facecolor(COR_CINZA)
        fig.tight_layout(pad=3.0)
        canvas.draw()
        return

    if not show_tilt and not show_vib:
        canvas.draw()
        if running:
            app.after(50, update_graph)
        return

    if show_tilt and show_vib:
        axs[0].set_visible(True)
        axs[1].set_visible(True)
        if tilts:
            suave = suavizar_fft(list(tilts))
            pts = list(range(len(suave)))
            axs[0].plot(pts, suave, color=COR_LARANJA, linewidth=2)
        axs[0].set_ylim(0, 100)
        axs[0].set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('Grau', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

        if vibracoes:
            suave = suavizar_fft(list(vibracoes))
            if UNIDADE_VIB_ATUAL == 'm/s²':
                suave = [g_para_ms2(v) for v in suave]
            pts = list(range(len(suave)))
            axs[1].plot(pts, suave, color='#FFB266', linewidth=2)
        
        if UNIDADE_VIB_ATUAL == 'm/s²':
            axs[1].set_ylim(0, 50)
        else:
            axs[1].set_ylim(0, 5)
            
        axs[1].set_title(f'Vibração ({unidade_display})', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[1].set_ylabel(unidade_display, color=COR_TEXTO)
        axs[1].set_facecolor(COR_CINZA)

    elif show_tilt:
        axs[0].set_visible(True)
        if tilts:
            suave = suavizar_fft(list(tilts))
            pts = list(range(len(suave)))
            axs[0].plot(pts, suave, color=COR_LARANJA, linewidth=2)
        axs[0].set_ylim(0, 100)
        axs[0].set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('Grau', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

    elif show_vib:
        axs[0].set_visible(True)
        if vibracoes:
            suave = suavizar_fft(list(vibracoes))
            if UNIDADE_VIB_ATUAL == 'm/s²':
                suave = [g_para_ms2(v) for v in suave]
            pts = list(range(len(suave)))
            axs[0].plot(pts, suave, color='#FFB266', linewidth=2)
        
        if UNIDADE_VIB_ATUAL == 'm/s²':
            axs[0].set_ylim(0, 50)
        else:
            axs[0].set_ylim(0, 5)
            
        axs[0].set_title(f'Vibração ({unidade_display})', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel(unidade_display, color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

    fig.tight_layout(pad=3.0)
    canvas.draw()
    
    if recording:
        capturar_frame_grafico()
    
    if running:
        app.after(100, update_graph)

grafico_tilt_var.trace_add('write', lambda *a: update_graph())
grafico_vib_var.trace_add('write', lambda *a: update_graph())

btn_frame = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
btn_frame.pack(pady=(10, 0))

# Inputs de limites
frame_limites = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
frame_limites.pack(fill='x', pady=(10, 0))

entry_tilt_limit = None
entry_vib_limit = None
label_tilt = None
label_vib = None
label_nenhum = None

def atualizar_limites_por_norma():
    """Atualiza os limites baseado na norma selecionada"""
    global TILT_THRESHOLD, VIB_THRESHOLD, ESTRUTURA_ATUAL, UNIDADE_VIB_ATUAL
    
    estrutura = estrutura_var.get()
    ESTRUTURA_ATUAL = estrutura
    
    if estrutura in estruturas_normas:
        norma_info = estruturas_normas[estrutura]
        
        info_text = f"{norma_info['norma']}\n{norma_info['descricao']}"
        label_info_norma.configure(text=info_text)
        
        if estrutura == 'Personalizada':
            UNIDADE_VIB_ATUAL = 'g'
        else:
            UNIDADE_VIB_ATUAL = 'm/s²'
        
        if entry_tilt_limit:
            entry_tilt_limit.delete(0, 'end')
            entry_tilt_limit.insert(0, str(norma_info['tilt']))
        
        if entry_vib_limit:
            entry_vib_limit.delete(0, 'end')
            if estrutura == 'Personalizada':
                entry_vib_limit.insert(0, str(norma_info['vib']))
            else:
                entry_vib_limit.insert(0, str(norma_info['vib']))
    
    atualizar_inputs_limites()
    atualizar_estado_iniciar()

def pode_iniciar():
    if not grafico_tilt_var.get() and not grafico_vib_var.get():
        return False
    if grafico_tilt_var.get():
        if not entry_tilt_limit or not entry_tilt_limit.get().strip():
            return False
        try:
            float(entry_tilt_limit.get())
        except:
            return False
    if grafico_vib_var.get():
        if not entry_vib_limit or not entry_vib_limit.get().strip():
            return False
        try:
            float(entry_vib_limit.get())
        except:
            return False
    return True

def atualizar_estado_iniciar(*args):
    if pode_iniciar():
        btn_start.configure(state='normal')
    else:
        btn_start.configure(state='disabled')

def atualizar_inputs_limites():
    global entry_tilt_limit, entry_vib_limit, label_tilt, label_vib, label_nenhum, UNIDADE_VIB_ATUAL
    for widget in frame_limites.winfo_children():
        widget.destroy()
    entry_tilt_limit = None
    entry_vib_limit = None
    label_tilt = None
    label_vib = None
    label_nenhum = None
    
    estrutura = estrutura_var.get()
    eh_personalizada = estrutura == 'Personalizada'
    
    if grafico_tilt_var.get():
        label_tilt = ctk.CTkLabel(frame_limites, text="Limite de inclinação (°):", font=('Segoe UI', 12))
        label_tilt.pack(pady=(0, 2))
        entry_tilt_limit = ctk.CTkEntry(frame_limites, width=100)
        
        if estrutura in estruturas_normas:
            valor_inicial = str(estruturas_normas[estrutura]['tilt'])
        else:
            valor_inicial = "80.0"
        entry_tilt_limit.insert(0, valor_inicial)
        entry_tilt_limit.pack(pady=(0, 8))
        entry_tilt_limit.bind('<KeyRelease>', lambda e: atualizar_estado_iniciar())
        
        if not eh_personalizada:
            entry_tilt_limit.configure(state='disabled')
    
    if grafico_vib_var.get():
        unidade_display = 'g' if eh_personalizada else 'm/s²'
        
        label_vib = ctk.CTkLabel(frame_limites, text=f"Limite de vibração ({unidade_display}):", font=('Segoe UI', 12))
        label_vib.pack(pady=(0, 2))
        entry_vib_limit = ctk.CTkEntry(frame_limites, width=100)
        
        if estrutura in estruturas_normas:
            valor_inicial = str(estruturas_normas[estrutura]['vib'])
        else:
            valor_inicial = "1.5"
        entry_vib_limit.insert(0, valor_inicial)
        entry_vib_limit.pack(pady=(0, 8))
        entry_vib_limit.bind('<KeyRelease>', lambda e: atualizar_estado_iniciar())
        
        if not eh_personalizada:
            entry_vib_limit.configure(state='disabled')
    
    if not grafico_tilt_var.get() and not grafico_vib_var.get():
        label_nenhum = ctk.CTkLabel(frame_limites, text="Nenhum gráfico selecionado", font=('Segoe UI', 12, 'italic'), text_color=COR_LARANJA)
        label_nenhum.pack(pady=10)
    atualizar_estado_iniciar()

grafico_tilt_var.trace_add('write', lambda *a: atualizar_estado_iniciar())
grafico_vib_var.trace_add('write', lambda *a: atualizar_estado_iniciar())

btn_start = ctk.CTkButton(
    frame_esquerdo, text='Iniciar',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=lambda: start_recepcao(),
    state='disabled'
)
btn_start.pack(side='bottom', pady=20)

def setup_inputs_iniciais():
    atualizar_limites_por_norma()
    atualizar_inputs_limites()
setup_inputs_iniciais()

# Lado direito
frame_passos = ctk.CTkFrame(frame_direito, fg_color='transparent')
frame_passos.pack(fill='both', expand=True)
label_passos = ctk.CTkLabel(
    frame_passos,
    text=(
        'Como usar o Riggy (EPUB):\n'
        '1. Selecione a norma técnica ou use "Personalizada".\n'
        '2. Selecione os gráficos desejados à esquerda.\n'
        '3. Para norma personalizada, defina os limites manualmente.\n'
        '4. Clique em Iniciar para começar a receber dados.\n'
        '5. Clique em Encerrar para parar a coleta.\n'
        '6. Gere o relatório em formato EPUB com vídeo embutido.'
    ),
    font=('Segoe UI', 15),
    justify='left',
    text_color=COR_TEXTO
)
label_passos.pack(padx=30, pady=30, anchor='center')

frame_graficos = ctk.CTkFrame(frame_direito, fg_color='transparent')
canvas.get_tk_widget().pack(fill='both', expand=True, pady=(0, 10))

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
    frame_botoes, text='Gerar relatório EPUB',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=gerar_relatorio_com_loading, state='disabled'
)
btn_report.pack(side='left', padx=10)

def atualizar_lado_direito(estado):
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

atualizar_lado_direito('passos')

def start_recepcao():
    global running, data_thread, TILT_THRESHOLD, VIB_THRESHOLD, encerrado
    reset_dados()
    
    iniciar_gravacao()
    
    try:
        if grafico_tilt_var.get() and entry_tilt_limit:
            TILT_THRESHOLD = float(entry_tilt_limit.get())
    except:
        TILT_THRESHOLD = 80.0
    try:
        if grafico_vib_var.get() and entry_vib_limit:
            VIB_THRESHOLD = float(entry_vib_limit.get())
    except:
        VIB_THRESHOLD = 1.5
    
    running = True
    encerrado = False
    status_label.configure(text='Recebendo...', text_color=COR_LARANJA)
    btn_start.configure(state='disabled')
    atualizar_lado_direito('graficos')
    
    data_thread = threading.Thread(target=processar_dados_thread, daemon=True)
    data_thread.start()
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
    tilts_all = []
    vibracoes_all = []

def stop_recepcao():
    global running, encerrado
    running = False
    encerrado = True
    status_label.configure(text='Parado', text_color=COR_LARANJA)
    btn_start.configure(state='normal')
    atualizar_lado_direito('encerrado')
    update_graph()

if __name__ == "__main__":
    app.mainloop()
