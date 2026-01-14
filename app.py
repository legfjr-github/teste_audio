import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc
from pydub import AudioSegment
import shutil
import zipfile

# --- CONFIGURAÇÃO DE CAMINHOS ---
path_to_ffmpeg = shutil.which("ffmpeg") 
path_to_ffprobe = shutil.which("ffprobe")
if path_to_ffmpeg: AudioSegment.converter = path_to_ffmpeg
if path_to_ffprobe: AudioSegment.ffprobe = path_to_ffprobe

st.set_page_config(page_title="Separador de Áudio", layout="centered")

st.title("Separador de Áudio (Low RAM) 🧹")
st.write("Otimizado para limpar a memória entre processos.")

# --- FUNÇÕES DE LIMPEZA ---
def limpar_memoria():
    """Força a limpeza do Garbage Collector e deleta variáveis pesadas"""
    gc.collect()
    
def resetar_sessao():
    """Apaga os caminhos antigos para liberar espaço para o novo"""
    keys_to_clear = ['path_voz', 'path_music', 'path_zip', 'processed']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    limpar_memoria()

# --- CARREGAMENTO DO MODELO ---
@st.cache_resource
def load_separator():
    # O modelo fica em cache, mas a execução será limpa
    return Separator('spleeter:2stems', multiprocess=False)

try:
    separator = load_separator()
    st.success("IA Pronta.")
except Exception as e:
    st.error(f"Erro IA: {e}")

# --- SIDEBAR ---
st.sidebar.header("Configurações")
chunk_len_sec = st.sidebar.slider("Tamanho do pedaço (seg)", 30, 60, 60)

uploaded_file = st.file_uploader("Escolha um arquivo", type=["mp3", "wav", "m4a"])

# --- PROCESSAMENTO ---
if uploaded_file is not None:
    # Botão principal
    if st.button("Iniciar Separação"):
        
        # 1. LIMPEZA CRÍTICA ANTES DE COMEÇAR
        # Se havia algo anterior, apagamos agora para dar lugar ao novo
        resetar_sessao()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner('Lendo e limpando memória...'):
                # Cria uma pasta temporária que vai persistir durante a sessão
                # Não usamos 'with tempfile...' aqui porque precisamos que o arquivo exista depois
                session_temp_dir = tempfile.mkdtemp()
                
                original_audio = AudioSegment.from_file(uploaded_file)
                
                # Divisão em chunks
                chunk_length_ms = chunk_len_sec * 1000
                chunks = [original_audio[i:i + chunk_length_ms] for i in range(0, len(original_audio), chunk_length_ms)]
                total_chunks = len(chunks)
                
                # Liberamos a memória do audio original, já temos os chunks
                del original_audio
                limpar_memoria()
                
                combined_vocals = AudioSegment.empty()
                combined_music = AudioSegment.empty()

                # Processamento dos pedaços
                for i, chunk in enumerate(chunks):
                    limpar_memoria() # Limpa a cada loop
                    step_percent = int((i / total_chunks) * 90)
                    progress_bar.progress(step_percent)
                    status_text.text(f"Processando parte {i+1}/{total_chunks}...")

                    # Processo padrão de salvar/separar/ler
                    chunk_path = os.path.join(session_temp_dir, f"temp_chunk.mp3")
                    chunk.export(chunk_path, format="mp3")
                    
                    try:
                        separator.separate_to_file(chunk_path, session_temp_dir, codec='mp3', bitrate='128k')
                    except Exception as e:
                        print(e)
                        continue

                    # Caminhos gerados pelo Spleeter
                    out_path = os.path.join(session_temp_dir, "temp_chunk") # Pasta criada pelo spleeter
                    v_path = os.path.join(out_path, "vocals.mp3")
                    m_path = os.path.join(out_path, "accompaniment.mp3")
                    
                    if os.path.exists(v_path):
                        combined_vocals += AudioSegment.from_mp3(v_path)
                    if os.path.exists(m_path):
                        combined_music += AudioSegment.from_mp3(m_path)
                
                # --- FINALIZAÇÃO E SALVAMENTO EM DISCO ---
                status_text.text("Salvando arquivos finais no disco...")
                
                # Caminhos finais
                final_voz_path = os.path.join(session_temp_dir, "voz_final.mp3")
                final_music_path = os.path.join(session_temp_dir, "playback_final.mp3")
                final_zip_path = os.path.join(session_temp_dir, "pacote_completo.zip")
                
                # Exporta para o DISCO (não RAM)
                combined_vocals.export(final_voz_path, format="mp3", bitrate="192k")
                combined_music.export(final_music_path, format="mp3", bitrate="192k")
                
                # Cria ZIP no DISCO
                with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(final_voz_path, "voz.mp3")
                    zf.write(final_music_path, "playback.mp3")
                
                # Salva os caminhos no session_state
                st.session_state.path_voz = final_voz_path
                st.session_state.path_music = final_music_path
                st.session_state.path_zip = final_zip_path
                st.session_state.processed = True
                
                # --- LIMPEZA PÓS-PROCESSO ---
                # Agora deletamos os objetos pesados do Python
                del combined_vocals
                del combined_music
                del chunks
                limpar_memoria()
                
                progress_bar.progress(100)
                status_text.text("Concluído!")
                st.rerun()

        except Exception as e:
            st.error(f"Erro: {e}")
            limpar_memoria()

# --- ÁREA DE DOWNLOAD (LÊ DO DISCO) ---
if 'processed' in st.session_state and st.session_state.processed:
    st.write("---")
    st.success("Arquivos prontos!")
    
    col1, col2, col3 = st.columns(3)
    
    # Função auxiliar para ler arquivo em bytes apenas na hora do clique
    def ler_arquivo(path):
        with open(path, "rb") as f:
            return f.read()

    try:
        with col1:
            st.subheader("🎤 Voz")
            # Nota: st.audio lê do path direto, economiza RAM
            st.audio(st.session_state.path_voz)
            st.download_button(
                "Baixar Voz", 
                data=ler_arquivo(st.session_state.path_voz), 
                file_name="voz.mp3", 
                mime="audio/mp3"
            )

        with col2:
            st.subheader("🎸 Playback")
            st.audio(st.session_state.path_music)
            st.download_button(
                "Baixar Playback", 
                data=ler_arquivo(st.session_state.path_music), 
                file_name="playback.mp3", 
                mime="audio/mp3"
            )

        with col3:
            st.subheader("📦 ZIP")
            st.write("Tudo junto:")
            st.download_button(
                "Baixar ZIP", 
                data=ler_arquivo(st.session_state.path_zip), 
                file_name="separados.zip", 
                mime="application/zip"
            )
            
    except FileNotFoundError:
        st.error("Arquivos expiraram. Por favor, processe novamente.")
        resetar_sessao()
        st.rerun()

    # Botão explícito para liberar tudo
    st.write("---")
    if st.button("🧹 Limpar tudo e recomeçar"):
        resetar_sessao()
        st.rerun()
