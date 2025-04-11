
import streamlit as st 
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

def main():
    st.set_page_config(page_title="Conferência de Medicamentos", layout="wide")
    st.markdown('<h5>Sistema de Conferência de Medicamentos</h5>', unsafe_allow_html=True)

    if "modo_conferencia" not in st.session_state:
        st.session_state["modo_conferencia"] = False

    if st.sidebar.button("Entrar no Modo de Conferência"):
        st.session_state["modo_conferencia"] = True

    if st.session_state["modo_conferencia"]:
        exibir_modo_conferencia()
        return

    uploaded_file = st.file_uploader("Faça upload do PDF do pedido:", type=["pdf"])

    if uploaded_file is not None and not st.session_state["modo_conferencia"]:
        st.session_state['uploaded_file'] = uploaded_file.read()

        padrao_item = re.compile(
            r"^(\d+)\s+"
            r"(\d+)\s+"
            r"(.+?)\s+"
            r"([A-Z0-9\-\/\.]+)\s+"
            r"([A-ZÇÀ-Úa-zçà-ú0-9º\.\-/]+)\s+"
            r"(\d+)$"
        )

        cabecalho_detalhes = {
            "Número do Pedido": "",
            "Ped. Solicitante": "",
            "Unidade Solicitante": "",
            "Estoque Solicitado": "",
            "Data/Hora": ""
        }

        itens = []
        captura = False

        with pdfplumber.open(BytesIO(st.session_state['uploaded_file'])) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linha in texto.splitlines():
                        linha = linha.strip()
                        if re.search(r"^(\d{7,})\s+.+\s+\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+\w+$", linha):
                            partes = linha.split()
                            cabecalho_detalhes["Número do Pedido"] = partes[0]
                            cabecalho_detalhes["Data/Hora"] = f"{partes[-3]} {partes[-2]}"
                            restante = partes[1:-3]
                            estoque_keywords = ["CAF", "GGE", "FARMÁCIA", "GERAL", "CENTRAL"]
                            for i in range(3, 0, -1):
                                trecho = ' '.join(restante[-i:]).upper()
                                if any(palavra in trecho for palavra in estoque_keywords):
                                    cabecalho_detalhes["Estoque Solicitado"] = trecho
                                    cabecalho_detalhes["Unidade Solicitante"] = ' '.join(restante[:-i])
                                    break
                            else:
                                cabecalho_detalhes["Unidade Solicitante"] = ' '.join(restante)
                            indice_unidade = next((i for i, p in enumerate(restante) if "-" in p), None)
                            if indice_unidade:
                                cabecalho_detalhes["Ped. Solicitante"] = ' '.join(restante[:indice_unidade])

                    for linha in texto.splitlines():
                        linha = linha.strip()
                        if linha.startswith("ITENS ATENDIDOS"):
                            captura = True
                            continue
                        if linha.startswith("ITENS NÃO ATENDIDOS"):
                            captura = False
                            continue
                        if captura:
                            m = padrao_item.match(linha)
                            if m:
                                num, pativo, principio, lote, und, qtd = m.groups()
                                itens.append({
                                    "Nº": int(num),
                                    "Pativo": int(pativo),
                                    "Princípio Ativo": principio.strip(),
                                    "Lote": lote,
                                    "Und.": und,
                                    "Qtd. p/Retirar": int(qtd),
                                    "Qtd. Disponível": ""  # começa vazio
                                })

        if itens:
            df = pd.DataFrame(itens)
            st.session_state['medicamentos'] = df.to_dict(orient='records')
            st.session_state['cabecalho'] = cabecalho_detalhes
            st.success(f"{len(df)} itens atendidos extraídos com sucesso.")
            st.subheader("📌 Informações do Pedido")
            for k, v in cabecalho_detalhes.items():
                st.markdown(f"**{k}:** {v}")

def exibir_modo_conferencia():
    st.markdown('<h5>Modo de Conferência</h5>', unsafe_allow_html=True)
    if 'medicamentos' not in st.session_state:
        st.warning("Nenhuma lista de medicamentos carregada.")
        return

    medicamentos = st.session_state['medicamentos']
    total = len(medicamentos)
    pagina = st.session_state.get('pagina_atual', 0)

    med = medicamentos[pagina]
    st.markdown(f"### {med['Princípio Ativo']}")
    st.markdown(f"**Unidade:** {med['Und.']} | **Solicitado:** {med['Qtd. p/Retirar']} ")

    qtd_chave = f"qtd_{pagina}"
    valor_inicial_qtd = st.session_state.get(qtd_chave, "")
    qtd_disp = st.text_input("Quantidade Disponível", value=valor_inicial_qtd, key=qtd_chave)
    st.session_state['medicamentos'][pagina]["Qtd. Disponível"] = qtd_disp

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Anterior") and pagina > 0:
            st.session_state['pagina_atual'] = pagina - 1
            st.rerun()
    with col2:
        if st.button("Próximo") and pagina < total - 1:
            st.session_state['pagina_atual'] = pagina + 1
            st.rerun()

    progresso = int(((pagina + 1) / total) * 100)
    st.progress(progresso, text=f"{pagina + 1} de {total}")

    with st.expander("🗃️ Visualizar Conferência Completa"):
        dados_pdf = []
        headers = ["#", "Princípio Ativo", "Lote", "Und.", "Qtd. p/Retirar", "Qtd. Disponível"]
        zerados = parciais = completos = 0

        for i, med in enumerate(medicamentos):
            solicitado = int(med["Qtd. p/Retirar"])
            try:
                qtd_disp = med.get("Qtd. Disponível", "").strip()
                qtd_disp_int = int(qtd_disp)
            except (ValueError, TypeError):
                qtd_disp_int = None

            if qtd_disp_int is None or qtd_disp == "":
                cor_linha = colors.white
            elif qtd_disp_int == 0:
                zerados += 1
                cor_linha = colors.red
            elif qtd_disp_int < solicitado:
                parciais += 1
                cor_linha = colors.orange
            else:
                completos += 1
                cor_linha = colors.lightgreen

            dados_pdf.append({
                "linha": [
                    med["Nº"],
                    med["Princípio Ativo"],
                    med["Lote"],
                    med["Und."],
                    solicitado,
                    qtd_disp if qtd_disp != "" else "-"
                ],
                "cor": cor_linha
            })

            st.markdown(f"**{i+1}. {med['Princípio Ativo']}**")
            st.markdown(f"- Lote: {med['Lote']} | Und.: {med['Und.']}")
            st.markdown(f"- Solicitado: {solicitado} | Disponível: {qtd_disp if qtd_disp != '' else '—'}")
            st.markdown("---")

        buffer_pdf = BytesIO()
        doc = SimpleDocTemplate(buffer_pdf, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elementos = []

        elementos.append(Paragraph("Relatório de Conferência de Medicamentos", styles['Title']))
        elementos.append(Spacer(1, 12))

        cabecalho = st.session_state.get("cabecalho", {})
        for k, v in cabecalho.items():
            elementos.append(Paragraph(f"<b>{k}:</b> {v}", styles['Normal']))
        elementos.append(Spacer(1, 12))

        elementos.append(Paragraph(f"<b>Total de Itens:</b> {len(medicamentos)}", styles['Normal']))
        elementos.append(Paragraph(f"<b>Completos:</b> {completos}", styles['Normal']))
        elementos.append(Paragraph(f"<b>Parciais:</b> {parciais}", styles['Normal']))
        elementos.append(Paragraph(f"<b>Zerados:</b> {zerados}", styles['Normal']))
        elementos.append(Spacer(1, 12))

        dados_tabela = [headers] + [d["linha"] for d in dados_pdf]
        tabela = Table(dados_tabela, repeatRows=1)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ])

        for i, dado in enumerate(dados_pdf, start=1):
            style.add('BACKGROUND', (0, i), (-1, i), dado["cor"])

        tabela.setStyle(style)
        elementos.append(tabela)

        elementos.append(Spacer(1, 36))
        elementos.append(Paragraph("Assinatura do Conferente: _____________________________________", styles['Normal']))
        elementos.append(Spacer(1, 12))
        elementos.append(Paragraph("Assinatura do Recebedor: _____________________________________", styles['Normal']))

        doc.build(elementos)

        st.download_button(
            label="📄 Baixar PDF da Conferência",
            data=buffer_pdf.getvalue(),
            file_name="relatorio_conferencia.pdf",
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
