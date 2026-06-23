-- =====================================================
-- TABELA USUARIOS
-- =====================================================

CREATE TABLE usuarios (
    id_usuario UUID PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,

    perfil VARCHAR(20) NOT NULL
    CHECK (perfil IN ('Aluno','Professor')),

    criado_em TIMESTAMP DEFAULT NOW()
);



-- =====================================================
-- TABELA AREAS
-- =====================================================

CREATE TABLE areas (
    id_area SERIAL PRIMARY KEY,
    nome VARCHAR(100) UNIQUE NOT NULL
);



-- =====================================================
-- TABELA RADICAIS
-- =====================================================

CREATE TABLE radicais (

    id_radical SERIAL PRIMARY KEY,

    nome VARCHAR(100) NOT NULL,

    significado TEXT NOT NULL,

    classificacao VARCHAR(20) NOT NULL
    CHECK (
        classificacao IN (
            'PREFIXO',
            'RADICAL',
            'SUFIXO'
        )
    ),

    fk_area INTEGER
    REFERENCES areas(id_area)
);



-- =====================================================
-- TABELA TERMOS
-- =====================================================

CREATE TABLE termos (

    id_termo SERIAL PRIMARY KEY,

    palavra_completa VARCHAR(200) NOT NULL,

    definicao_biologica TEXT NOT NULL,

    fk_area INTEGER
    REFERENCES areas(id_area),

    criado_por UUID
    REFERENCES usuarios(id_usuario),

    criado_pelo_professor BOOLEAN DEFAULT FALSE,

    criado_em TIMESTAMP DEFAULT NOW()
);



-- =====================================================
-- RELAÇÃO TERMO X RADICAL
-- =====================================================

CREATE TABLE termo_radicais (

    id SERIAL PRIMARY KEY,

    fk_termo INTEGER NOT NULL
    REFERENCES termos(id_termo)
    ON DELETE CASCADE,

    fk_radical INTEGER NOT NULL
    REFERENCES radicais(id_radical)
    ON DELETE CASCADE,

    ordem INTEGER NOT NULL,

    UNIQUE(fk_termo, ordem)
);



-- =====================================================
-- TURMAS
-- =====================================================

CREATE TABLE turmas (

    id_turma SERIAL PRIMARY KEY,

    nome VARCHAR(150) NOT NULL,

    codigo VARCHAR(6) UNIQUE NOT NULL,

    fk_professor UUID NOT NULL
    REFERENCES usuarios(id_usuario),

    criado_em TIMESTAMP DEFAULT NOW()
);



-- =====================================================
-- MATRICULAS DOS ALUNOS
-- =====================================================

CREATE TABLE usuario_turma (

    id SERIAL PRIMARY KEY,

    fk_usuario UUID NOT NULL
    REFERENCES usuarios(id_usuario)
    ON DELETE CASCADE,

    fk_turma INTEGER NOT NULL
    REFERENCES turmas(id_turma)
    ON DELETE CASCADE,

    pontuacao INTEGER DEFAULT 0,

    data_ingresso TIMESTAMP DEFAULT NOW(),

    UNIQUE(fk_usuario, fk_turma)
);



-- =====================================================
-- TRILHAS
-- =====================================================

CREATE TABLE trilhas (

    id_trilha SERIAL PRIMARY KEY,

    nome VARCHAR(150) NOT NULL,

    fk_professor UUID NOT NULL
    REFERENCES usuarios(id_usuario),

    criado_em TIMESTAMP DEFAULT NOW()
);



-- =====================================================
-- TERMOS DA TRILHA
-- =====================================================

CREATE TABLE trilha_termos (

    id SERIAL PRIMARY KEY,

    fk_trilha INTEGER NOT NULL
    REFERENCES trilhas(id_trilha)
    ON DELETE CASCADE,

    fk_termo INTEGER NOT NULL
    REFERENCES termos(id_termo)
    ON DELETE CASCADE,

    UNIQUE(fk_trilha, fk_termo)
);



-- =====================================================
-- TRILHAS ATRIBUIDAS A TURMAS
-- =====================================================

CREATE TABLE turma_trilha (

    id SERIAL PRIMARY KEY,

    fk_turma INTEGER NOT NULL
    REFERENCES turmas(id_turma)
    ON DELETE CASCADE,

    fk_trilha INTEGER NOT NULL
    REFERENCES trilhas(id_trilha)
    ON DELETE CASCADE,

    UNIQUE(fk_turma, fk_trilha)
);



-- =====================================================
-- PROGRESSO DOS ALUNOS
-- =====================================================

CREATE TABLE usuario_trilha_termo (

    id SERIAL PRIMARY KEY,

    fk_usuario UUID NOT NULL
    REFERENCES usuarios(id_usuario)
    ON DELETE CASCADE,

    fk_turma_trilha INTEGER NOT NULL
    REFERENCES turma_trilha(id)
    ON DELETE CASCADE,

    fk_termo INTEGER NOT NULL
    REFERENCES termos(id_termo)
    ON DELETE CASCADE,

    acertou BOOLEAN DEFAULT FALSE,

    data_conclusao TIMESTAMP,

    UNIQUE(
        fk_usuario,
        fk_turma_trilha,
        fk_termo
    )
);



-- =====================================================
-- FLASHCARDS
-- =====================================================

CREATE TABLE flashcards (

    id_flashcard SERIAL PRIMARY KEY,

    fk_usuario UUID NOT NULL
    REFERENCES usuarios(id_usuario)
    ON DELETE CASCADE,

    fk_termo INTEGER NOT NULL
    REFERENCES termos(id_termo)
    ON DELETE CASCADE,

    ativo BOOLEAN DEFAULT TRUE,

    dificuldade VARCHAR(20)
    CHECK (
        dificuldade IN (
            'facil',
            'medio',
            'dificil'
        )
    ),

    proxima_revisao_em TIMESTAMP,

    criado_em TIMESTAMP DEFAULT NOW(),

    UNIQUE(fk_usuario, fk_termo)
);



-- =====================================================
-- RPC PARA PONTUAÇÃO
-- =====================================================

CREATE OR REPLACE FUNCTION incrementar_pontuacao(
    p_usuario UUID,
    p_turma INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS
$$
BEGIN

    UPDATE usuario_turma

    SET pontuacao = pontuacao + 10

    WHERE
        fk_usuario = p_usuario
        AND
        fk_turma = p_turma;

END;
$$;