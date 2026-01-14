import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc
from pydub import AudioSegment

st.set_page_config(page_title="Separador de Áudio", layout="centered")

st.title("Separador de Áudio (Modo Segmentado) ✂️")
st.write("Processa músicas longas cortando em pedaços para economizar memória.")

# Configurações
st.sidebar.header("Configurações")
stems = st.sidebar.selectbox("Tipo de separação", ["2 stems (Voz + Música)"])
chunk_len_sec = st.sidebar.slider("Tamanho do pedaço (seg)", 30, 60, 60, help="60s é o ideal. Se travar, diminua.")

@st.cache_resource
def load_separator():
    # multiprocess=False continua sendo essencial
    return Separator('spleeter:2stems', multiprocess=False)

try:
    separator = load_separator()
    st.success("Modelo IA carregado!")
except Exception as e:
    st.error(f"Erro ao carregar modelo: {e}")

uploaded_file = st.file_uploader("Escolha um arquivo mp3/wav/m4a", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    if st.button("Separar Áudio Completo"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner('Lendo arquivo original...'):
                # Carrega o áudio completo usando Pydub
                original_audio = AudioSegment.from_file(uploaded_file)
                
                # Calcula quantos pedaços teremos
                chunk_length_ms = chunk_len_sec * 1000
                chunks = [original_audio[i:i + chunk_length_ms] for i in range(0, len(original_audio), chunk_length_ms)]
                total_chunks = len(chunks)
                
                status_text.text(f"Áudio dividido em {total_chunks} partes. Iniciando processamento...")
                
                # Listas para guardar os pedaços processados
                combined_vocals = AudioSegment.empty()
                combined_music = AudioSegment.empty()

                # Diretório temporário mestre
                with tempfile.TemporaryDirectory() as master_temp_dir:
                    
                    for i, chunk in enumerate(chunks):
                        gc.collect() # Limpa memória antes de cada loop
                        
                        step_percent = int((i / total_chunks) * 100)
                        progress_bar.progress(step_percent)
                        status_text.text(f"Processando parte {i+1} de {total_chunks}...")

                        # 1. Salva o pedaço atual num arquivo temporário
                        chunk_filename = f"chunk_{i}.mp3"
                        chunk_path = os.path.join(master_temp_dir, chunk_filename)
                        
                        # Exporta o pedaço para o disco para o Spleeter ler
                        chunk.export(chunk_path, format="mp3")
                        
                        # 2. Roda o Spleeter neste pedaço
                        # Nota: O Spleeter cria uma pasta com o nome do arquivo (sem extensão)
                        separator.separate_to_file(
                            chunk_path, 
                            master_temp_dir, 
                            codec='mp3', 
                            bitrate='128k'
                        )
                        
                        # 3. Recupera os arquivos gerados
                        chunk_folder_name = f"chunk_{i}"
                        output_path = os.path.join(master_temp_dir, chunk_folder_name)
                        
                        vocals_chunk_path = os.path.join(output_path, "vocals.mp3")
                        music_chunk_path = os.path.join(output_path, "accompaniment.mp3")
                        
                        # 4. Carrega os resultados de volta para o Pydub e adiciona à lista final
                        # Usamos crossfade=0 para colar seco, ou um valor pequeno se quiser suavizar
                        if os.path.exists(vocals_chunk_path):
                            seg_v = AudioSegment.from_mp3(vocals_chunk_path)
                            combined_vocals += seg_v
                        
                        if os.path.exists(music_chunk_path):
                            seg_m = AudioSegment.from_mp3(music_chunk_path)
                            combined_music += seg_m
                            
                        # Limpeza extra de arquivos já usados para não lotar o disco
                        try:
                            # Opcional: deletar os arquivos mp3 parciais se o disco estiver muito cheio
                            pass 
                        except:
                            pass

                # Finalização
                progress_bar.progress(90)
                status_text.text("Unindo as partes finais...")
                
                # Exporta os arquivos finais para download
                # Precisamos salvar em buffer ou arquivo temporário para o botão de download ler
                
                # Cria arquivos finais em outro temp ou na memória
                final_vocals_path = os.path.join(master_temp_dir, "final_vocals.mp3") # Esse path vai falhar pq o dir fecha
                # Vamos usar buffers de bytes para download direto
                from io import BytesIO
                
                buffer_voz = BytesIO()
                combined_vocals.export(buffer_voz, format="mp3", bitrate="192k")
                
                buffer_music = BytesIO()
                combined_music.export(buffer_music, format="mp3", bitrate="192k")
                
                progress_bar.progress(100)
                status_text.text("Processamento concluído!")
                
                st.write("---")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🎤 Voz Completa")
                    st.download_button(
                        label="Baixar Voz",
                        data=buffer_voz.getvalue(),
                        file_name="voz_completa.mp3",
                        mime="audio/mp3"
                    )
                    
                with col2:
                    st.subheader("🎸 Música Completa")
                    st.download_button(
                        label="Baixar Playback",
                        data=buffer_music.getvalue(),
                        file_name="playback_completo.mp3",
                        mime="audio/mp3"
                    )

        except Exception as e:
            st.error(f"Erro crítico: {e}")
            st.warning("Se o erro for de memória, tente diminuir o tamanho do pedaço para 30s.")
            
        finally:
            gc.collect()
