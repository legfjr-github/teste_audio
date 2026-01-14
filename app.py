import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc
from pydub import AudioSegment, effects
import shutil
import zipfile

# --- CONFIGURAÇÃO DE CAMINHOS ---
path_to_ffmpeg = shutil.which("ffmpeg") 
path_to_ffprobe = shutil.which("ffprobe")
if path_to_ffmpeg: AudioSegment.converter = path_to_ffmpeg
if path_to_ffprobe: AudioSegment.ffprobe = path_to_ffprobe

st.set_page_config(page_title="Separador PRO", layout="centered")

st.title("Separador de Áudio PRO (Alta Qualidade) 🎧")
st.write("Usa modelo de 16kHz, normalização e fusão suave (crossfade).")

# --- FUNÇÕES DE LIMPEZA ---
def limpar_memoria():
    gc.collect()
    
def resetar_sessao():
    keys_to_clear = ['path_voz', 'path_music', 'path_zip', 'processed']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    limpar_memoria()

# --- CARREGAMENTO DO MODELO (AGORA 16kHz) ---
@st.cache_resource
def load_separator():
    # MUDANÇA 1: Usamos o modelo '-16kHz' que tem mais brilho e menos som abafado
    return Separator('spleeter:2stems-16kHz', multiprocess=False)

try:
    separator = load_separator()
    st.success("IA de Alta Fidelidade (16kHz) Pronta.")
except Exception as e:
    st.error(f"Erro IA: {e}")

# --- SIDEBAR ---
st.sidebar.header("Configurações Avançadas")
chunk_len_sec = st.sidebar.slider("Tamanho do Bloco (seg)", 30, 60, 60)
crossfade_ms = st.sidebar.slider("Suavização/Overlap (ms)", 0, 3000, 1000, help="Tempo de fusão entre os blocos para evitar cortes.")
aplicar_norm = st.sidebar.checkbox("Normalizar Áudio (Melhor volume)", value=True)

uploaded_file = st.file_uploader("Escolha um arquivo", type=["mp3", "wav", "m4a"])

# --- PROCESSAMENTO ---
if uploaded_file is not None:
    if st.button("Iniciar Separação PRO"):
        resetar_sessao()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner('Analisando áudio...'):
                session_temp_dir = tempfile.mkdtemp()
                
                original_audio = AudioSegment.from_file(uploaded_file)
                
                # --- MUDANÇA 2: LÓGICA DE OVERLAP ---
                # Definimos o tamanho do passo (o quanto andamos pra frente)
                step_ms = chunk_len_sec * 1000
                # O chunk será o tamanho do passo + o tempo de crossfade (para ter o que fundir)
                chunk_total_ms = step_ms + crossfade_ms
                
                # Criar lista de coordenadas de corte
                # Ex: 0, 60000, 120000...
                starts = range(0, len(original_audio), step_ms)
                
                total_chunks = len(starts)
                
                # Preparamos a base vazia
                combined_vocals = AudioSegment.empty()
                combined_music = AudioSegment.empty()

                # Loop inteligente
                for i, start_time in enumerate(starts):
                    limpar_memoria()
                    
                    # Barra de progresso
                    step_percent = int((i / total_chunks) * 90)
                    progress_bar.progress(step_percent)
                    status_text.text(f"Otimizando bloco {i+1}/{total_chunks}...")

                    # Corta o pedaço COM sobra para o crossfade
                    # O 'end_time' vai um pouco além do step se não for o último
                    end_time = min(start_time + chunk_total_ms, len(original_audio))
                    chunk = original_audio[start_time:end_time]
                    
                    # Salva e processa
                    chunk_path = os.path.join(session_temp_dir, f"temp_chunk.mp3")
                    chunk.export(chunk_path, format="mp3")
                    
                    try:
                        separator.separate_to_file(chunk_path, session_temp_dir, codec='mp3', bitrate='192k')
                    except Exception as e:
                        print(e)
                        continue

                    out_path = os.path.join(session_temp_dir, "temp_chunk")
                    v_path = os.path.join(out_path, "vocals.mp3")
                    m_path = os.path.join(out_path, "accompaniment.mp3")
                    
                    if os.path.exists(v_path) and os.path.exists(m_path):
                        seg_v = AudioSegment.from_mp3(v_path)
                        seg_m = AudioSegment.from_mp3(m_path)
                        
                        # --- MUDANÇA 3: CROSSFADE NA JUNÇÃO ---
                        if i == 0:
                            # Primeiro pedaço só adiciona
                            combined_vocals += seg_v
                            combined_music += seg_m
                        else:
                            # Pedaços seguintes usam crossfade
                            # O append com crossfade funde o final do audio atual com o inicio do novo
                            combined_vocals = combined_vocals.append(seg_v, crossfade=crossfade_ms)
                            combined_music = combined_music.append(seg_m, crossfade=crossfade_ms)

                del original_audio
                limpar_memoria()

                status_text.text("Aplicando pós-processamento (EQ e Volume)...")
                
                # --- PÓS-PROCESSAMENTO ---
                if aplicar_norm:
                    # Normaliza (Aumenta o volume sem distorcer)
                    combined_vocals = effects.normalize(combined_vocals)
                    combined_music = effects.normalize(combined_music)
                    
                    # Pequeno filtro para remover "ruído surdo" (High Pass Filter)
                    # Remove frequências abaixo de 80Hz da voz (limpa o som)
                    combined_vocals = combined_vocals.high_pass_filter(80)

                # Exportação final
                final_voz_path = os.path.join(session_temp_dir, "voz_final.mp3")
                final_music_path = os.path.join(session_temp_dir, "playback_final.mp3")
                final_zip_path = os.path.join(session_temp_dir, "pacote_completo.zip")
                
                combined_vocals.export(final_voz_path, format="mp3", bitrate="192k")
                combined_music.export(final_music_path, format="mp3", bitrate="192k")
                
                with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(final_voz_path, "voz.mp3")
                    zf.write(final_music_path, "playback.mp3")
                
                st.session_state.path_voz = final_voz_path
                st.session_state.path_music = final_music_path
                st.session_state.path_zip = final_zip_path
                st.session_state.processed = True
                
                # Limpeza final
                del combined_vocals
                del combined_music
                limpar_memoria()
                
                progress_bar.progress(100)
                status_text.text("Concluído!")
                st.rerun()

        except Exception as e:
            st.error(f"Erro: {e}")
            limpar_memoria()

# --- ÁREA DE DOWNLOAD ---
if 'processed' in st.session_state and st.session_state.processed:
    st.write("---")
    st.success("Áudio Otimizado Pronto!")
    
    col1, col2, col3 = st.columns(3)
    
    def ler_arquivo(path):
        with open(path, "rb") as f:
            return f.read()

    try:
        with col1:
            st.subheader("🎤 Voz")
            st.audio(st.session_state.path_voz)
            st.download_button("Baixar Voz", data=ler_arquivo(st.session_state.path_voz), file_name="voz_pro.mp3", mime="audio/mp3")

        with col2:
            st.subheader("🎸 Playback")
            st.audio(st.session_state.path_music)
            st.download_button("Baixar Playback", data=ler_arquivo(st.session_state.path_music), file_name="playback_pro.mp3", mime="audio/mp3")

        with col3:
            st.subheader("📦 ZIP")
            st.write("Pacote:")
            st.download_button("Baixar ZIP", data=ler_arquivo(st.session_state.path_zip), file_name="separados_pro.zip", mime="application/zip")
            
    except FileNotFoundError:
        st.error("Arquivos expiraram.")
        resetar_sessao()
        st.rerun()

    st.write("---")
    if st.button("🧹 Limpar e Recomeçar"):
        resetar_sessao()
        st.rerun()
