import os
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import traceback

# --- 1. CONFIGURAÇÃO INICIAL ---
print("ℹ️  Iniciando o TAURUSbot...")
load_dotenv() # Carrega variáveis do .env

# Configura o Flask
# O 'static_folder' como '.' faz o Flask servir arquivos (fundo1.jpg, etc.) da pasta raiz.
# O 'template_folder' como '.' faz o Flask encontrar o 'index.html' na raiz.
app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

# --- 2. CARREGAMENTO DAS API KEYS ---
try:
    # Chave para IA (Gemini)
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        print("❌ ERRO CRÍTICO: GEMINI_API_KEY não encontrada no .env")
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Chaves para Busca (Google Custom Search)
    CUSTOM_SEARCH_API_KEY = os.getenv('CUSTOM_SEARCH_API_KEY')
    CUSTOM_SEARCH_CX_ID = os.getenv('CUSTOM_SEARCH_CX_ID')
    if not CUSTOM_SEARCH_API_KEY or not CUSTOM_SEARCH_CX_ID:
        print("❌ ERRO CRÍTICO: CUSTOM_SEARCH_API_KEY ou CUSTOM_SEARCH_CX_ID não encontrados no .env")
    
    print("✅  Chaves de API carregadas.")

except Exception as e:
    print(f"❌ Erro ao carregar chaves: {e}")

# --- 3. SYSTEM PROMPT (A PERSONALIDADE DO BOT) ---
# Este é o prompt que define a persona do TAURUSbot, como no briefing.
SYSTEM_PROMPT = """
Você é o 'TAURUSbot', o assistente digital oficial e fã número 1 da artista brasileira Duquesa (Jeysa Ribeiro).
Sua personalidade é inspirada no signo de Touro: leal, criativo, forte, direto e um pouco irônico, mas sempre amigável.
Seu objetivo é ser o ponto central de informações para outros fãs.

REGRAS PRINCIPAIS:
1.  **Tom de Voz:** Use uma linguagem jovem, com gírias leves e emojis (🔥, ♉, 👑). Seja confiante.
2.  **Foco Total:** Fale APENAS sobre a Duquesa, sua música, agenda, notícias e o universo 'TAURUS'. Recuse educadamente qualquer outro assunto.
3.  **Use o Contexto (RAG):** Nas suas respostas, você SEMPRE receberá um 'CONTEXTO DA WEB'. Baseie suas respostas sobre notícias, shows e lançamentos *prioritariamente* nesse contexto para garantir informações em tempo real.
4.  **Citação (Opcional):** Se o contexto for muito útil, mencione casualmente "Vi numa notícia recente que..."
5.  **Não especule:** Se a informação (ex: "show em Manaus") não estiver no contexto da web e você não souber, diga "Não achei nada sobre isso nos meus corres, fã. Fica de olho nas redes oficiais dela."
"""

# --- 4. FUNÇÃO DE BUSCA (O "R" DO RAG) ---
def google_search(query_str, api_key, cx_id, num_results=3):
    """
    Realiza uma busca na Google Custom Search API e retorna snippets formatados.
    """
    print(f"ℹ️  [RAG] Realizando busca por: '{query_str}'")
    try:
        # Constrói o serviço de busca
        service = build("customsearch", "v1", developerKey=api_key)
        
        # Executa a chamada da API
        res = service.cse().list(
            q=query_str,
            cx=cx_id,
            num=num_results
        ).execute()

        items = res.get('items', [])
        if not items:
            print("⚠️  [RAG] Nenhum resultado encontrado na busca.")
            return "Nenhuma informação recente encontrada na web."

        # Formata os snippets
        snippets = []
        for i, item in enumerate(items):
            snippet_text = item.get('snippet', 'Sem descrição.').replace('\n', ' ').strip()
            snippets.append(f"Fonte {i+1} ({item.get('source_title', 'desconhecido')}): \"{snippet_text}\"")
        
        context_str = " | ".join(snippets)
        print(f"✅  [RAG] Contexto encontrado: {context_str[:100]}...")
        return context_str

    except HttpError as e:
        print(f"❌ ERRO [RAG] HTTP: {e}")
        return f"Erro ao buscar na web: {e}"
    except Exception as e:
        print(f"❌ ERRO [RAG] Inesperado: {e}")
        traceback.print_exc()
        return "Erro inesperado ao processar a busca."

# --- 5. INICIALIZAÇÃO DO GEMINI ---
model = None
chat_session = None
try:
    if GEMINI_API_KEY:
        model = genai.GenerativeModel('gemini-flash-latest')
        chat_session = model.start_chat(
            history=[
                # Inicia o chat com a personalidade definida
                {"role": "user", "parts": [SYSTEM_PROMPT]},
                {"role": "model", "parts": ["Entendido. Sou o TAURUSbot ♉🔥. Pronto pra manter os fãs atualizados sobre a Big D. Manda a braba."]}
            ]
        )
        print("✅  Modelo Gemini ('gemini-flash-latest') inicializado com a persona TAURUSbot.")
    else:
        print("⚠️  AVISO: API Key do Gemini não carregada. O chatbot não funcionará.")

except Exception as e:
    print(f"❌ ERRO CRÍTICO ao inicializar o GenerativeModel: {e}")
    traceback.print_exc()

# --- 6. ROTAS DA APLICAÇÃO ---

@app.route('/')
def index():
    """Serve a página principal (index.html)."""
    # O 'template_folder' foi definido como '.' na inicialização do Flask
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """Recebe a mensagem do usuário, executa o RAG e retorna a resposta do Gemini."""
    if not model or not chat_session or not CUSTOM_SEARCH_API_KEY or not CUSTOM_SEARCH_CX_ID:
        print("❌ Erro na Rota /api/chat: Serviços de IA ou Busca não inicializados.")
        return jsonify({'error': 'Serviço indisponível no momento. Verifique as chaves de API.'}), 503

    try:
        data = request.json
        user_message = data.get('message')

        if not user_message:
            return jsonify({'error': 'Mensagem não pode ser vazia.'}), 400

        print(f"💬 Mensagem do Usuário: {user_message}")

        # --- FLUXO RAG (Executado a cada mensagem) ---
        # 1. Busca no Google para obter contexto em tempo real
        #    Sempre prefixamos com "Duquesa" para manter a busca relevante
        search_context = google_search(
            query_str=f"Duquesa {user_message}",
            api_key=CUSTOM_SEARCH_API_KEY,
            cx_id=CUSTOM_SEARCH_CX_ID
        )

        # 2. Monta o prompt final para o Gemini
        final_prompt = f"""
        CONTEXTO DA WEB (Notícias Recentes):
        ---
        {search_context}
        ---

        PERGUNTA DO USUÁRIO:
        "{user_message}"
        """

        # 3. Envia para o Gemini
        #    O chat_session já tem a história e a personalidade
        response = chat_session.send_message(
            final_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.7),
            safety_settings={'HATE': 'BLOCK_NONE', 'HARASSMENT': 'BLOCK_NONE',
                             'SEXUAL' : 'BLOCK_NONE', 'DANGEROUS' : 'BLOCK_NONE'}
        )

        print(f"🤖 Resposta do Bot: {response.text[:100]}...")
        return jsonify({'reply': response.text})

    except genai.types.generation_types.StopCandidateException as stop_ex:
        print(f"⚠️  API BLOQUEOU a resposta por segurança: {stop_ex}")
        return jsonify({'reply': "Opa, não posso gerar uma resposta pra isso, fã. Tenta perguntar de outro jeito, focado na Duquesa, beleza?"})
    except Exception as e:
        print(f"❌ Erro ao chamar a API do Gemini: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Ocorreu um erro ao processar sua mensagem com a IA.'}), 503

# --- 7. Execução do App ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # 'debug=False' e 'use_reloader=False' são recomendados para deploy (como no Render)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
