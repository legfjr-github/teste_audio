import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc
from pydub import AudioSegment, effects
import shutil
import zipfile
from pytubefix import YouTube 
from pytubefix.cli import on_progress

# --- CONFIGURAÇÃO INICIAL ---
path_to_ffmpeg = shutil.which("ffmpeg") 
path_to_ffprobe = shutil.which("ffprobe")
if path_to_ffmpeg: AudioSegment.converter = path_to_ffmpeg
if path_to_ffprobe: AudioSegment.ffprobe = path_to_ffprobe

st.set_page_config(page_title="Studio AI", layout="centered")
st.title("Studio de Áudio & Vídeo IA 🎥🎵")
st.write("Baixe vídeos, converta mp3 ou separe voz e instrumentos (IA).")

# --- ESTADO E VARIÁVEIS ---
if 'yt_object' not in st.session_state: st.session_state.yt_object = None # Guarda o objeto YouTube
if 'processed' not in st.session_state: st.session_state.processed = False

vars_path = ['path_voz', 'path_music', 'path_zip', 'path_video_download', 'path_audio_download']
for v in vars_path:
    if v not in st.session_state: st.session_state[v] = None

# --- FUNÇÕES DE LIMPEZA E UTILITÁRIAS ---
def limpar_memoria():
    gc.collect()

def resetar_sessao(keep_yt=False):
    keys_to_clear = vars_path + ['processed']
    for key in keys_to_clear:
        if key in st.session_state:
            st.session_state[key] = None
    if not keep_yt:
        st.session_state.yt_object = None
    limpar_memoria()

def ler_arquivo(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

# --- CARREGAMENTO IA ---
@st.cache_resource
def load_separator():
    return Separator('spleeter:2stems-16kHz', multiprocess=False)

try:
    separator = load_separator()
except Exception as e:
    st.error(f"Erro IA: {e}")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configurações IA")
chunk_len_sec = st.sidebar.slider("Tamanho do Bloco (seg)", 30, 60, 60)
crossfade_ms = st.sidebar.slider("Overlap (ms)", 0, 3000, 1000)
aplicar_norm = st.sidebar.checkbox("Normalizar", value=True)

# --- PROCESSAMENTO IA (SPLEETER) ---
def processar_separacao_audio(source_path, status_placeholder, progress_bar):
    try:
        session_temp_dir = tempfile.mkdtemp()
        status_placeholder.text("Lendo áudio...")
        
        # Converte para wav/mp3 garantido antes de ler, para evitar erros de formato
        audio_seg = AudioSegment.from_file(source_path)
        
        step_ms = chunk_len_sec * 1000
        chunk_total_ms = step_ms + crossfade_ms
        starts = range(0, len(audio_seg), step_ms)
        total_chunks = len(starts)
        
        combined_vocals = AudioSegment.empty()
        combined_music = AudioSegment.empty()

        for i, start_time in enumerate(starts):
            limpar_memoria()
            progress_bar.progress(int((i / total_chunks) * 80))
            status_placeholder.text(f"Processando IA: {i+1}/{total_chunks}...")

            end_time = min(start_time + chunk_total_ms, len(audio_seg))
            chunk = audio_seg[start_time:end_time]
            
            chunk_path = os.path.join(session_temp_dir, f"temp_chunk.mp3")
            chunk.export(chunk_path, format="mp3")
            
            try:
                separator.separate_to_file(chunk_path, session_temp_dir, codec='mp3', bitrate='192k')
            except:
                continue

            out_path = os.path.join(session_temp_dir, "temp_chunk")
            v_path = os.path.join(out_path, "vocals.mp3")
            m_path = os.path.join(out_path, "accompaniment.mp3")
            
            if os.path.exists(v_path) and os.path.exists(m_path):
                seg_v = AudioSegment.from_mp3(v_path)
                seg_m = AudioSegment.from_mp3(m_path)
                
                if i == 0:
                    combined_vocals += seg_v
                    combined_music += seg_m
                else:
                    combined_vocals = combined_vocals.append(seg_v, crossfade=crossfade_ms)
                    combined_music = combined_music.append(seg_m, crossfade=crossfade_ms)

        del audio_seg
        limpar_memoria()

        status_placeholder.text("Finalizando...")
        if aplicar_norm:
            combined_vocals = effects.normalize(combined_vocals)
            combined_music = effects.normalize(combined_music)
            combined_vocals = combined_vocals.high_pass_filter(80)

        final_voz_path = os.path.join(session_temp_dir, "voz_final.mp3")
        final_music_path = os.path.join(session_temp_dir, "playback_final.mp3")
        final_zip_path = os.path.join(session_temp_dir, "pacote_ia.zip")
        
        combined_vocals.export(final_voz_path, format="mp3", bitrate="192k")
        combined_music.export(final_music_path, format="mp3", bitrate="192k")
        
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(final_voz_path, "voz.mp3")
            zf.write(final_music_path, "playback.mp3")
        
        st.session_state.path_voz = final_voz_path
        st.session_state.path_music = final_music_path
        st.session_state.path_zip = final_zip_path
        st.session_state.processed = True
        
        progress_bar.progress(100)
        status_placeholder.text("Concluído!")
        del combined_vocals
        del combined_music
        limpar_memoria()
        
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        limpar_memoria()

# --- FUNÇÕES YOUTUBE (PYTUBEFIX) ---
def get_yt_object(url):
    try:
        # Pytubefix tenta corrigir o token automaticamente
        yt = YouTube(url)
        return yt
    except Exception as e:
        return None

def download_video_pytube(yt, resolution):
    """Baixa vídeo (MP4)"""
    temp_dir = tempfile.mkdtemp()
    # Filtra pelo 'res' (ex: '720p') e garante que tem audio e video (progressive=True) ou adapta
    # Progressive=True é mais seguro, mas limita a 720p. 
    # Para 1080p precisaria baixar separado e juntar, vamos simplificar com progressive primeiro.
    stream = yt.streams.filter(res=resolution, progressive=True, file_extension='mp4').first()
    
    if not stream:
        # Fallback: Tenta qualquer stream com essa resolução ou a maior possível
        stream = yt.streams.get_by_resolution(resolution)
        if not stream:
            stream = yt.streams.get_highest_resolution()
            
    filename = stream.download(output_path=temp_dir)
    return filename

def download_audio_pytube(yt, for_ai=False):
    """Baixa apenas áudio e converte para MP3"""
    temp_dir = tempfile.mkdtemp()
    
    # Baixa o stream apenas de áudio (geralmente mp4/m4a ou webm)
    stream = yt.streams.get_audio_only()
    downloaded_file = stream.download(output_path=temp_dir)
    
    # Converte para MP3 usando Pydub (mais compatível que o arquivo cru)
    base, _ = os.path.splitext(downloaded_file)
    mp3_filename = base + ".mp3"
    
    # Conversão
    audio = AudioSegment.from_file(downloaded_file)
    audio.export(mp3_filename, format="mp3", bitrate="192k")
    
    # Remove o arquivo original (m4a/webm) para economizar espaço
    try:
        os.remove(downloaded_file)
    except: pass
    
    return mp3_filename

# ================= INTERFACE =================

tab_upload, tab_youtube = st.tabs(["📂 Arquivo Local", "🔗 Link do YouTube"])

with tab_upload:
    uploaded_file = st.file_uploader("Envie seu arquivo", type=["mp3", "wav", "m4a"])
    if uploaded_file and st.button("Separar (Upload)"):
        resetar_sessao()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name
        prog_bar = st.progress(0)
        status_txt = st.empty()
        processar_separacao_audio(tmp_path, status_txt, prog_bar)
        st.rerun()

with tab_youtube:
    yt_url = st.text_input("Link do YouTube:")
    
    if st.button("🔍 Analisar"):
        if yt_url:
            with st.spinner("Conectando ao YouTube..."):
                yt = get_yt_object(yt_url)
                if yt:
                    try:
                        # Força checar se o título existe para validar o link (dispara o erro 403 aqui se der)
                        title = yt.title 
                        st.session_state.yt_object = yt
                        resetar_sessao(keep_yt=True)
                    except Exception as e:
                        st.error(f"Erro ao acessar vídeo (Bloqueio ou link inválido): {e}")
                else:
                    st.error("Link inválido.")
    
    # Se já temos o objeto YT carregado
    if st.session_state.yt_object:
        yt = st.session_state.yt_object
        try:
            st.subheader(yt.title)
            st.image(yt.thumbnail_url, width=300)
            
            action = st.radio("Ação:", ["Baixar Áudio (MP3)", "Baixar Vídeo (MP4)", "Separar Voz/Playback (IA)"])
            
            if action == "Baixar Vídeo (MP4)":
                # Lista resoluções disponíveis (streams progressivos para evitar erro de ffmpeg merge)
                streams = yt.streams.filter(progressive=True, file_extension='mp4')
                res_options = sorted(list(set([s.resolution for s in streams if s.resolution])), reverse=True)
                
                if not res_options:
                    res_options = ["720p (Padrão)"] # Fallback
                
                selected_res = st.selectbox("Resolução:", res_options)
                
                if st.button("⬇️ Baixar Vídeo"):
                    with st.spinner("Baixando..."):
                        try:
                            v_path = download_video_pytube(yt, selected_res)
                            st.session_state.path_video_download = v_path
                            st.success("Vídeo pronto!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro download: {e}")

            elif action == "Baixar Áudio (MP3)":
                if st.button("⬇️ Baixar MP3"):
                    with st.spinner("Baixando e convertendo..."):
                        try:
                            a_path = download_audio_pytube(yt)
                            st.session_state.path_audio_download = a_path
                            st.success("Áudio pronto!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro download: {e}")

            elif action == "Separar Voz/Playback (IA)":
                if st.button("🚀 Iniciar IA"):
                    with st.spinner("Baixando áudio para processamento..."):
                        try:
                            temp_audio_path = download_audio_pytube(yt, for_ai=True)
                            prog_bar = st.progress(0)
                            status_txt = st.empty()
                            processar_separacao_audio(temp_audio_path, status_txt, prog_bar)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")
        except Exception as e:
            st.error("Sessão do YouTube expirou. Analise o link novamente.")
            st.session_state.yt_object = None

# ================= ÁREA DE DOWNLOADS =================
st.write("---")

if st.session_state.processed:
    st.subheader("🎵 IA Resultados")
    c1, c2, c3 = st.columns(3)
    try:
        with c1: st.download_button("🎤 Voz", ler_arquivo(st.session_state.path_voz), "voz.mp3", "audio/mp3")
        with c2: st.download_button("🎸 Playback", ler_arquivo(st.session_state.path_music), "playback.mp3", "audio/mp3")
        with c3: st.download_button("📦 ZIP", ler_arquivo(st.session_state.path_zip), "ia.zip", "application/zip")
    except: pass

if st.session_state.path_video_download:
    st.subheader("🎬 Vídeo")
    path = st.session_state.path_video_download
    try:
        st.video(path)
        st.download_button("💾 Salvar Vídeo", ler_arquivo(path), os.path.basename(path), "video/mp4")
    except: pass

if st.session_state.path_audio_download:
    st.subheader("🎵 Áudio")
    path = st.session_state.path_audio_download
    try:
        st.audio(path)
        st.download_button("💾 Salvar MP3", ler_arquivo(path), os.path.basename(path), "audio/mp3")
    except: pass

if st.button("🧹 Limpar Tudo"):
    resetar_sessao()
    st.rerun()
