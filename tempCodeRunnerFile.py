import os
import json
import random
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client, Client
from dotenv import load_dotenv

# Carrego as variáveis de ambiente do arquivo .env
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')

# Configuro a conexão com o Supabase usando credenciais seguras
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------------------------------------------
# Decorador para exigir autenticação via token JWT do Supabase
# -------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"erro": "Token de acesso ausente ou inválido"}), 401
        token = auth_header.split(' ')[1]
        try:
            # Verifico o token e obtenho os dados do usuário logado
            user_response = supabase.auth.get_user(token)
            request.user = user_response.user
        except Exception as e:
            return jsonify({"erro": "Falha na autenticação"}), 401
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# Rotas de autenticação (registro e login)
# -------------------------------------------------------------------
@app.route('/api/auth/register', methods=['POST'])
def register():
    # Aqui eu crio a rota para cadastrar um novo usuário
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    nome = data.get('nome')
    perfil = data.get('perfil')  # 'Aluno' ou 'Professor'

    if not all([email, password, nome, perfil]):
        return jsonify({"erro": "Campos obrigatórios: email, password, nome, perfil"}), 400
    if perfil not in ('Aluno', 'Professor'):
        return jsonify({"erro": "Perfil deve ser 'Aluno' ou 'Professor'"}), 400

    try:
        # Registro no sistema de autenticação do Supabase
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        user_id = auth_response.user.id

        # Insere o perfil complementar na tabela 'usuarios'
        supabase.table("usuarios").insert({
            "id_usuario": user_id,
            "nome": nome,
            "email": email,
            "perfil": perfil,
            "criado_em": datetime.utcnow().isoformat()
        }).execute()

        return jsonify({"mensagem": "Usuário criado com sucesso", "user_id": user_id}), 201
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    # Crio a rota de login que retorna o token de acesso
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"erro": "Email e senha são obrigatórios"}), 400

    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return jsonify({
            "access_token": auth_response.session.access_token,
            "user_id": auth_response.user.id
        }), 200
    except Exception as e:
        return jsonify({"erro": "Credenciais inválidas"}), 401

# -------------------------------------------------------------------
# Perfil do usuário logado
# -------------------------------------------------------------------
@app.route('/api/user/profile', methods=['GET'])
@login_required
def get_profile():
    # Busco os dados do usuário na tabela 'usuarios' usando o ID do token
    user_id = request.user.id
    response = supabase.table("usuarios").select("*").eq("id_usuario", user_id).execute()
    if response.data:
        return jsonify(response.data[0]), 200
    return jsonify({"erro": "Usuário não encontrado"}), 404

# -------------------------------------------------------------------
# Termos e Radicais (leitura a partir do banco populado via seed)
# -------------------------------------------------------------------
@app.route('/api/terms', methods=['GET'])
def list_terms():
    # Filtro os termos de acordo com os parâmetros enviados
    tipo = request.args.get('tipo')      # 'complexos' ou 'radicais_isolados'
    area = request.args.get('area')      # filtra por área (ex: "Citologia")

    if tipo == 'radicais_isolados':
        # Retorna radicais puros (prefixos e sufixos)
        query = supabase.table("radicais").select("*")
        if area:
            # Para simplificar, o campo área não existe em radicais; busco por termos relacionados
            # mas posso permitir filtrar por classificação
            pass
        rad_response = query.execute()
        return jsonify(rad_response.data), 200

    # Se tipo == 'complexos' (padrão) ou não informado
    query = supabase.table("termos").select("*, termo_radicais(radicais(*))")
    if area:
        # Supondo que o JSON original tenha 'area'; replicado em campo na tabela termos
        query = query.eq("area", area)
    termos_response = query.execute()
    return jsonify(termos_response.data), 200

@app.route('/api/terms/<term_id>', methods=['GET'])
def get_term(term_id):
    # Retorno um termo específico com seus radicais associados
    response = supabase.table("termos").select("*, termo_radicais(radicais(*))").eq("id_termo", term_id).execute()
    if response.data:
        return jsonify(response.data[0]), 200
    return jsonify({"erro": "Termo não encontrado"}), 404

@app.route('/api/radicais/<radical_id>/terms', methods=['GET'])
def get_terms_by_radical(radical_id):
    # Busco todos os termos que contêm um determinado radical
    associations = supabase.table("termo_radicais").select("termos(*)").eq("fk_radical", radical_id).execute()
    termos = [item['termos'] for item in associations.data if item.get('termos')]
    return jsonify(termos), 200

# -------------------------------------------------------------------
# Turmas (criação, ingresso, listagem, remoção de alunos)
# -------------------------------------------------------------------
@app.route('/api/turmas', methods=['POST'])
@login_required
def criar_turma():
    # Apenas professores podem criar turmas
    user_id = request.user.id
    user_profile = supabase.table("usuarios").select("perfil").eq("id_usuario", user_id).execute()
    if not user_profile.data or user_profile.data[0]['perfil'] != 'Professor':
        return jsonify({"erro": "Apenas professores podem criar turmas"}), 403

    data = request.get_json()
    nome_turma = data.get('nome')
    if not nome_turma:
        return jsonify({"erro": "Nome da turma é obrigatório"}), 400

    # Gero um código alfanumérico único (6 caracteres)
    codigo = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
    # Garanto que o código seja único
    while supabase.table("turmas").select("id_turma").eq("codigo", codigo).execute().data:
        codigo = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))

    new_turma = {
        "nome": nome_turma,
        "codigo": codigo,
        "fk_professor": user_id,
        "criado_em": datetime.utcnow().isoformat()
    }
    result = supabase.table("turmas").insert(new_turma).execute()
    if result.data:
        return jsonify(result.data[0]), 201
    return jsonify({"erro": "Erro ao criar turma"}), 500

@app.route('/api/turmas', methods=['GET'])
@login_required
def listar_turmas():
    # Lista as turmas do usuário (como professor ou aluno)
    user_id = request.user.id
    perfil = supabase.table("usuarios").select("perfil").eq("id_usuario", user_id).execute().data[0]['perfil']

    if perfil == 'Professor':
        turmas = supabase.table("turmas").select("*").eq("fk_professor", user_id).execute()
    else:
        # Aluno: turmas onde está matriculado via tabela associativa usuario_turma
        matriculas = supabase.table("usuario_turma").select("fk_turma").eq("fk_usuario", user_id).execute()
        turmas_ids = [m['fk_turma'] for m in matriculas.data]
        if turmas_ids:
            turmas = supabase.table("turmas").select("*").in_("id_turma", turmas_ids).execute()
        else:
            turmas = {"data": []}
    return jsonify(turmas.data), 200

@app.route('/api/turmas/join', methods=['POST'])
@login_required
def ingressar_turma():
    # Aluno ingressa em uma turma usando código
    user_id = request.user.id
    data = request.get_json()
    codigo = data.get('codigo')
    if not codigo:
        return jsonify({"erro": "Código da turma é obrigatório"}), 400

    turma = supabase.table("turmas").select("*").eq("codigo", codigo).execute()
    if not turma.data:
        return jsonify({"erro": "Turma não encontrada"}), 404

    turma_id = turma.data[0]['id_turma']
    # Verifico se já está matriculado
    exist = supabase.table("usuario_turma").select("*").eq("fk_usuario", user_id).eq("fk_turma", turma_id).execute()
    if exist.data:
        return jsonify({"mensagem": "Você já está nesta turma"}), 200

    # Insere matrícula
    supabase.table("usuario_turma").insert({
        "fk_usuario": user_id,
        "fk_turma": turma_id,
        "pontuacao": 0,
        "data_ingresso": datetime.utcnow().isoformat()
    }).execute()
    return jsonify({"mensagem": "Ingressou na turma com sucesso"}), 201

@app.route('/api/turmas/<turma_id>/alunos', methods=['GET'])
@login_required
def listar_alunos_turma(turma_id):
    # Lista os alunos de uma turma (professor vê todos, aluno vê colegas)
    matriculas = supabase.table("usuario_turma").select("fk_usuario, usuarios(nome, email)").eq("fk_turma", turma_id).execute()
    alunos = []
    for m in matriculas.data:
        user = m['usuarios']
        alunos.append({
            "id_usuario": m['fk_usuario'],
            "nome": user['nome'],
            "email": user['email']
        })
    return jsonify(alunos), 200

@app.route('/api/turmas/<turma_id>/alunos/<aluno_id>', methods=['DELETE'])
@login_required
def remover_aluno(turma_id, aluno_id):
    # Apenas professor da turma pode remover aluno
    user_id = request.user.id
    turma = supabase.table("turmas").select("fk_professor").eq("id_turma", turma_id).execute()
    if not turma.data or turma.data[0]['fk_professor'] != user_id:
        return jsonify({"erro": "Permissão negada"}), 403

    supabase.table("usuario_turma").delete().eq("fk_turma", turma_id).eq("fk_usuario", aluno_id).execute()
    return jsonify({"mensagem": "Aluno removido da turma"}), 200

# -------------------------------------------------------------------
# Trilhas (criação, atribuição a turmas e progresso)
# -------------------------------------------------------------------
@app.route('/api/trilhas', methods=['POST'])
@login_required
def criar_trilha():
    # Professor cria uma trilha com nome e lista de IDs de termos
    user_id = request.user.id
    data = request.get_json()
    nome = data.get('nome')
    term_ids = data.get('termos')  # lista de IDs de termos

    if not nome or not term_ids:
        return jsonify({"erro": "Nome e termos são obrigatórios"}), 400

    # Insere a trilha
    trilha_resp = supabase.table("trilhas").insert({
        "nome": nome,
        "fk_professor": user_id,
        "criado_em": datetime.utcnow().isoformat()
    }).execute()
    trilha_id = trilha_resp.data[0]['id_trilha']

    # Associa os termos à trilha (tabela trilha_termos)
    for tid in term_ids:
        supabase.table("trilha_termos").insert({
            "fk_trilha": trilha_id,
            "fk_termo": tid
        }).execute()

    return jsonify({"mensagem": "Trilha criada", "id_trilha": trilha_id}), 201

@app.route('/api/turmas/<turma_id>/trilhas', methods=['POST'])
@login_required
def atribuir_trilha_turma(turma_id):
    # Professor atribui uma trilha existente a uma turma (instância separada)
    user_id = request.user.id
    data = request.get_json()
    trilha_id = data.get('trilha_id')
    if not trilha_id:
        return jsonify({"erro": "trilha_id é obrigatório"}), 400

    # Verifica se professor é dono da turma e da trilha
    turma = supabase.table("turmas").select("fk_professor, nome").eq("id_turma", turma_id).execute()
    trilha = supabase.table("trilhas").select("fk_professor, nome").eq("id_trilha", trilha_id).execute()
    if not turma.data or not trilha.data:
        return jsonify({"erro": "Turma ou trilha inválida"}), 404
    if turma.data[0]['fk_professor'] != user_id or trilha.data[0]['fk_professor'] != user_id:
        return jsonify({"erro": "Permissão negada"}), 403

    # Cria instância de turma_trilha com nome composto (ex: Citologia 2A)
    nome_instancia = f"{trilha.data[0]['nome']} {turma.data[0]['nome']}"
    instancia = supabase.table("turma_trilha").insert({
        "fk_turma": turma_id,
        "fk_trilha": trilha_id,
        "nome_instancia": nome_instancia,
        "data_atribuicao": datetime.utcnow().isoformat()
    }).execute()

    return jsonify({"mensagem": "Trilha atribuída à turma", "turma_trilha_id": instancia.data[0]['id']}), 201

@app.route('/api/turmas/<turma_id>/trilhas', methods=['GET'])
@login_required
def listar_trilhas_turma(turma_id):
    # Retorna todas as trilhas atribuídas a uma turma específica
    instancias = supabase.table("turma_trilha").select("*, trilhas(nome)").eq("fk_turma", turma_id).execute()
    return jsonify(instancias.data), 200

# -------------------------------------------------------------------
# Jogos (Montagem e Decifrador) – lógica de negócio completa
# -------------------------------------------------------------------
@app.route('/api/jogos/montagem/start', methods=['GET'])
@login_required
def iniciar_montagem():
    # Inicio o jogo de montagem: seleciono um termo e envio suas definições e radicais embaralhados
    trilha_id = request.args.get('trilha_id')  # opcional
    if trilha_id:
        # Seleciono termo aleatório da trilha
        termos_rel = supabase.table("trilha_termos").select("fk_termo").eq("fk_trilha", trilha_id).execute()
        if not termos_rel.data:
            return jsonify({"erro": "Trilha sem termos"}), 404
        term_ids = [t['fk_termo'] for t in termos_rel.data]
        termo_id = random.choice(term_ids)
    else:
        # Seleciono um termo aleatório do banco completo
        all_terms = supabase.table("termos").select("id_termo").execute()
        if not all_terms.data:
            return jsonify({"erro": "Nenhum termo disponível"}), 404
        termo_id = random.choice(all_terms.data)['id_termo']

    # Busco termo com radicais e ordem
    termo = supabase.table("termos").select("*, termo_radicais(ordem, radicais(*))").eq("id_termo", termo_id).execute().data[0]

    # Preparo a definição
    definicao = termo['definicao_biologica']
    # Monto lista de radicais com id, nome e se é prefixo/sufixo
    radicais_opcoes = []
    for tr in termo['termo_radicais']:
        rad = tr['radicais']
        radicais_opcoes.append({
            "id_radical": rad['id_radical'],
            "nome": rad['nome'],
            "classificacao": rad['classificacao'],
            "ordem": tr['ordem']
        })
    # Embaralho a lista de opções (mas mantenho a ordem correta escondida)
    random.shuffle(radicais_opcoes)

    return jsonify({
        "termo_id": termo_id,
        "definicao": definicao,
        "radicais": radicais_opcoes,
        "tipo": "montagem"
    }), 200

@app.route('/api/jogos/montagem/answer', methods=['POST'])
@login_required
def verificar_montagem():
    # Verifico se a ordem dos radicais enviada está correta
    data = request.get_json()
    termo_id = data.get('termo_id')
    ordem_usuario = data.get('ordem')  # lista de IDs de radicais na ordem escolhida
    turma_id = data.get('turma_id')    # opcional, para pontuação
    trilha_id = data.get('trilha_id')  # opcional, para progresso

    if not termo_id or not ordem_usuario:
        return jsonify({"erro": "Dados insuficientes"}), 400

    # Busco a ordem correta dos radicais do termo
    associacoes = supabase.table("termo_radicais").select("ordem, fk_radical").eq("fk_termo", termo_id).order("ordem").execute()
    ordem_correta = [a['fk_radical'] for a in associacoes.data]

    if ordem_usuario == ordem_correta:
        # Acertou! Registro pontuação se turma_id presente
        if turma_id:
            # Incremento pontuação do aluno na turma
            supabase.rpc("incrementar_pontuacao", {"p_usuario": request.user.id, "p_turma": turma_id}).execute()
        # Se foi dentro de uma trilha, marco progresso no termo
        if trilha_id and turma_id:
            # Encontro a instância turma_trilha
            turma_trilha = supabase.table("turma_trilha").select("id").eq("fk_turma", turma_id).eq("fk_trilha", trilha_id).execute()
            if turma_trilha.data:
                turma_trilha_id = turma_trilha.data[0]['id']
                # Registro acerto do termo (se ainda não existir)
                supabase.table("usuario_trilha_termo").upsert({
                    "fk_usuario": request.user.id,
                    "fk_turma_trilha": turma_trilha_id,
                    "fk_termo": termo_id,
                    "acertou": True
                }, on_conflict="fk_usuario, fk_turma_trilha, fk_termo").execute()

        # Gero flashcard automaticamente
        flashcard = criar_flashcard_automatico(request.user.id, termo_id)
        return jsonify({
            "correto": True,
            "flashcard": flashcard
        }), 200
    else:
        return jsonify({"correto": False}), 200

@app.route('/api/jogos/decifrador/start', methods=['GET'])
@login_required
def iniciar_decifrador():
    # Inicio jogo de decifrador: seleciono um termo e preparo 4 alternativas
    trilha_id = request.args.get('trilha_id')
    if trilha_id:
        termos_rel = supabase.table("trilha_termos").select("fk_termo").eq("fk_trilha", trilha_id).execute()
        if not termos_rel.data:
            return jsonify({"erro": "Trilha sem termos"}), 404
        term_ids = [t['fk_termo'] for t in termos_rel.data]
        termo_id = random.choice(term_ids)
    else:
        all_terms = supabase.table("termos").select("id_termo").execute()
        if not all_terms.data:
            return jsonify({"erro": "Nenhum termo disponível"}), 404
        termo_id = random.choice(all_terms.data)['id_termo']

    termo = supabase.table("termos").select("*").eq("id_termo", termo_id).execute().data[0]
    palavra = termo['palavra_completa']
    definicao_correta = termo['definicao_biologica']

    # Seleciono 3 definições incorretas aleatórias de outros termos
    outras_definicoes = supabase.table("termos").select("definicao_biologica").neq("id_termo", termo_id).limit(3).execute()
    opcoes = [definicao_correta] + [d['definicao_biologica'] for d in outras_definicoes.data]
    random.shuffle(opcoes)
    indice_correto = opcoes.index(definicao_correta)

    return jsonify({
        "termo_id": termo_id,
        "palavra": palavra,
        "opcoes": opcoes,
        "indice_correto": indice_correto,
        "tipo": "decifrador"
    }), 200

@app.route('/api/jogos/decifrador/answer', methods=['POST'])
@login_required
def verificar_decifrador():
    # Verifico se a alternativa escolhida é a correta
    data = request.get_json()
    termo_id = data.get('termo_id')
    resposta_usuario = data.get('resposta')  # índice ou definição; usarei índice
    turma_id = data.get('turma_id')
    trilha_id = data.get('trilha_id')

    if not termo_id or resposta_usuario is None:
        return jsonify({"erro": "Dados insuficientes"}), 400

    # Recalculo a resposta correta (o backend já sabe)
    termo = supabase.table("termos").select("definicao_biologica").eq("id_termo", termo_id).execute().data[0]
    # Para verificar, preciso ter as mesmas opções que enviei; como stateless, confio no índice enviado
    # Mas o ideal é manter um estado; para simplificar, aceito o índice e comparo com o que foi enviado.
    # Como não tenho estado, assumo que o front passou as mesmas opções e apenas o índice.
    # Aqui apenas verifico se o índice corresponde ao índice correto enviado anteriormente (inseguro).
    # Solução: reenvio as opções no start e depois verifico se o índice bate com a definição correta.
    # Por isso, no answer, preciso receber também as opções? Opto por receber a string da definição escolhida.
    # Melhor: front envia a definição escolhida (texto).
    definicao_escolhida = data.get('definicao_escolhida')
    if definicao_escolhida == termo['definicao_biologica']:
        # Acertou
        if turma_id:
            supabase.rpc("incrementar_pontuacao", {"p_usuario": request.user.id, "p_turma": turma_id}).execute()
        if trilha_id and turma_id:
            turma_trilha = supabase.table("turma_trilha").select("id").eq("fk_turma", turma_id).eq("fk_trilha", trilha_id).execute()
            if turma_trilha.data:
                supabase.table("usuario_trilha_termo").upsert({
                    "fk_usuario": request.user.id,
                    "fk_turma_trilha": turma_trilha.data[0]['id'],
                    "fk_termo": termo_id,
                    "acertou": True
                }, on_conflict="fk_usuario, fk_turma_trilha, fk_termo").execute()

        flashcard = criar_flashcard_automatico(request.user.id, termo_id)
        return jsonify({"correto": True, "flashcard": flashcard}), 200
    else:
        return jsonify({"correto": False}), 200

# -------------------------------------------------------------------
# Flashcards (criação automática, listagem, revisão e cancelamento)
# -------------------------------------------------------------------
def criar_flashcard_automatico(user_id, termo_id):
    # Crio ou reativo um flashcard para o usuário e termo, se necessário
    existente = supabase.table("flashcards").select("*").eq("fk_usuario", user_id).eq("fk_termo", termo_id).execute()
    if existente.data:
        # Se já existe e está ativo, retorno sem alterar
        if existente.data[0]['ativo']:
            return {"id": existente.data[0]['id_flashcard'], "show_modal": False}
        else:
            # Reativo o flashcard cancelado anteriormente
            supabase.table("flashcards").update({"ativo": True}).eq("id_flashcard", existente.data[0]['id_flashcard']).execute()
            return {"id": existente.data[0]['id_flashcard'], "show_modal": True}
    else:
        # Crio um novo flashcard
        novo = supabase.table("flashcards").insert({
            "fk_usuario": user_id,
            "fk_termo": termo_id,
            "ativo": True,
            "dificuldade": "fácil",  # padrão inicial
            "criado_em": datetime.utcnow().isoformat()
        }).execute()
        return {"id": novo.data[0]['id_flashcard'], "show_modal": True}

@app.route('/api/flashcards', methods=['GET'])
@login_required
def listar_flashcards():
    user_id = request.user.id
    dificuldade = request.args.get('dificuldade')  # 'fácil', 'difícil' ou None para todos
    query = supabase.table("flashcards").select("*, termos(palavra_completa, definicao_biologica)").eq("fk_usuario", user_id).eq("ativo", True)
    if dificuldade:
        query = query.eq("dificuldade", dificuldade)
    result = query.execute()
    return jsonify(result.data), 200

@app.route('/api/flashcards/<flashcard_id>/review', methods=['PUT'])
@login_required
def revisar_flashcard(flashcard_id):
    # Atualizo dificuldade baseado se acertou ou errou
    data = request.get_json()
    acertou = data.get('acertou')  # boolean
    if acertou is None:
        return jsonify({"erro": "Campo 'acertou' obrigatório"}), 400

    nova_dificuldade = "fácil" if acertou else "difícil"
    supabase.table("flashcards").update({"dificuldade": nova_dificuldade}).eq("id_flashcard", flashcard_id).eq("fk_usuario", request.user.id).execute()
    return jsonify({"mensagem": "Revisão registrada"}), 200

@app.route('/api/flashcards/<flashcard_id>', methods=['DELETE'])
@login_required
def cancelar_flashcard(flashcard_id):
    # O usuário pode cancelar (desativar) um flashcard recém-criado
    supabase.table("flashcards").update({"ativo": False}).eq("id_flashcard", flashcard_id).eq("fk_usuario", request.user.id).execute()
    return jsonify({"mensagem": "Flashcard cancelado"}), 200

# -------------------------------------------------------------------
# Ranking (por turma)
# -------------------------------------------------------------------
@app.route('/api/ranking', methods=['GET'])
@login_required
def obter_ranking():
    turma_id = request.args.get('turma_id')
    if not turma_id:
        return jsonify({"erro": "turma_id é obrigatório"}), 400

    # Busco todos os alunos da turma com suas pontuações, ordenado decrescente
    ranking = supabase.table("usuario_turma").select("fk_usuario, pontuacao, usuarios(nome)").eq("fk_turma", turma_id).order("pontuacao", desc=True).execute()
    return jsonify(ranking.data), 200

# -------------------------------------------------------------------
# Gráfico de progresso das trilhas para o professor
# -------------------------------------------------------------------
@app.route('/api/graph/progresso', methods=['GET'])
@login_required
def progresso_trilhas_turma():
    turma_id = request.args.get('turma_id')
    if not turma_id:
        return jsonify({"erro": "turma_id é obrigatório"}), 400

    # Verifico se o usuário é professor da turma
    user_id = request.user.id
    turma = supabase.table("turmas").select("fk_professor").eq("id_turma", turma_id).execute()
    if not turma.data or turma.data[0]['fk_professor'] != user_id:
        return jsonify({"erro": "Acesso negado"}), 403

    # Obtenho todas as instâncias de trilhas atribuídas à turma
    instancias = supabase.table("turma_trilha").select("id, nome_instancia, fk_trilha").eq("fk_turma", turma_id).execute()
    resultado = []
    for inst in instancias.data:
        turma_trilha_id = inst['id']
        # Total de alunos na turma
        total_alunos = supabase.table("usuario_turma").select("fk_usuario", count="exact").eq("fk_turma", turma_id).execute().count
        # Total de termos na trilha original
        total_termos = supabase.table("trilha_termos").select("fk_termo", count="exact").eq("fk_trilha", inst['fk_trilha']).execute().count
        # Alunos que completaram (têm todos os termos acertados)
        # Para cada aluno, verifico quantos termos distintos acertou para essa instância
        alunos_progresso = supabase.table("usuario_trilha_termo").select("fk_usuario").eq("fk_turma_trilha", turma_trilha_id).eq("acertou", True).execute()
        # Conto quantos termos únicos cada aluno acertou
        from collections import Counter
        contagem = Counter(item['fk_usuario'] for item in alunos_progresso.data)
        completos = sum(1 for count in contagem.values() if count == total_termos)
        resultado.append({
            "nome_instancia": inst['nome_instancia'],
            "total_alunos": total_alunos,
            "total_termos": total_termos,
            "alunos_completaram": completos,
            "porcentagem": (completos / total_alunos * 100) if total_alunos > 0 else 0
        })

    return jsonify(resultado), 200

# -------------------------------------------------------------------
# Rota de seed (popular banco com JSON) – uso administrativo
# -------------------------------------------------------------------
@app.route('/api/seed', methods=['POST'])
def seed_database():
    # Rota protegida por chave simples (apenas para desenvolvimento)
    token = request.headers.get('X-Seed-Key')
    if token != os.getenv('SEED_KEY', 'lise123'):
        return jsonify({"erro": "Não autorizado"}), 403

    # Carrego o arquivo JSON com os dados iniciais
    with open('terms.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Insiro radicais
    for r in data.get('radicais', []):
        supabase.table("radicais").upsert({
            "nome": r['nome'],
            "significado": r['significado'],
            "classificacao": r['classificacao']
        }, on_conflict="nome").execute()

    # Insiro termos e associoções
    for t in data.get('termos', []):
        termo_insert = supabase.table("termos").insert({
            "palavra_completa": t['palavra'],
            "definicao_biologica": t['definicao'],
            "nivel_hierarquico": t.get('nivel_hierarquico', 'Organísmico'),
            "area": t.get('area', 'Geral')
        }).execute()
        termo_id = termo_insert.data[0]['id_termo']

        # Crio as ligações na tabela termo_radicais
        for idx, rad_info in enumerate(t['radicais']):
            # Busco o radical pelo nome
            rad = supabase.table("radicais").select("id_radical").eq("nome", rad_info['nome']).execute()
            if rad.data:
                rad_id = rad.data[0]['id_radical']
                ordem = rad_info.get('ordem', idx+1)
                supabase.table("termo_radicais").insert({
                    "fk_termo": termo_id,
                    "fk_radical": rad_id,
                    "ordem": ordem
                }).execute()

    return jsonify({"mensagem": "Banco populado com sucesso"}), 201

# -------------------------------------------------------------------
# Servindo arquivos estáticos do front-end
# -------------------------------------------------------------------
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    # Sirvo qualquer arquivo da pasta templates (HTML, CSS, JS)
    return send_from_directory('templates', filename)

# -------------------------------------------------------------------
# Execução da aplicação
# -------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)