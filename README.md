# 🚀 Taxi Data ETL Portfolio

## Transformando dados em insights com Inteligência Artificial

**Engenharia de Dados** | **LLM Operations** | **AI-Driven Development**

---

## 🎯 O que eu construí

Projeto de **ETL de dados de taxi da NYC** que utiliza **opencode** com **Qwen 3.5 9B** para acelerar o desenvolvimento de pipelines de dados.

**Objetivo**: Criar **agents especializados** que extraiam o máximo valor de LLMs para automatizar e otimizar processos de engenharia de dados.

### 🧠 Minha abordagem

Utilizo **LLMs para acelerar o processo de engenharia de dados**:

- **Geração automática** de código de pipelines ETL
- **Refatoração inteligente** para otimização de performance
- **Documentação automática** com exemplos práticos
- **Debug assistido** por IA para redução de bugs

---

## 🛠️ Stack Tecnológica

```
┌─────────────────────────────────────────┐
│         LLM & AI Tools                   │
│  • opencode CLI                         │
│  • Qwen 3.5 9B                          │
│  • Prompt Engineering                   │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         Data Engineering Stack           │
│  • Python                               │
│  • AWS S3                               │
│  • ClickHouse                           │
└─────────────────────────────────────────┘
```

---

## 📁 Estrutura do Projeto

```
taxi-data-etl/
├── extract/              # Extração de dados da NYC
├── upload/               # Upload para S3
├── orchestrator/         # Orquestração do pipeline
├── scripts/              # Scripts utilitários
├── mutants/              # Testes de mutação
├── tests/                # Testes abrangentes
├── .github/              # CI/CD workflows
├── .hypothesis/          # Fuzz testing
├── .coverage             # Cobertura de testes
└── pyproject.toml        # Configuração do projeto
```

## 🧪 Estratégia de Testes

Implementei uma **estratégia de testes em camadas** para garantir qualidade:

### 🎯 Testes Unitários
- Testam componentes individuais isoladamente
- Feedback rápido durante o desenvolvimento
- Cobertura de funções críticas

### 🧪 Testes E2E (End-to-End)
- Validação completa do fluxo do download ao upload
- Testes com mocks de API (respx, vcrpy)
- Verificação do processo completo

### 🐛 Testes de Fuzzing
- Envio de dados aleatórios e malformados
- Encontra edge cases que testes manuais não descobrem
- Usa hypothesis para geração de dados

### 🧬 Testes de Mutação
- Mutação testing com mutmut
- Garante que testes detectam bugs reais
- Identifica testes fracos que precisam ser melhorados

### 🔬 Análise de Qualidade

Utilizei ferramentas para analisar o código:

- **Radon**: Medição de complexidade ciclomática e cobertura
- **Xenon**: Análise de qualidade de código
- **Coverage.py**: Rastreamento de execução de código
- **Mutmut**: Testes de mutação para validar testes

Isso me permitiu:
- Identificar áreas do código com baixa cobertura
- Encontrar funções complexas que precisam de refatoração
- Detectar código não utilizado (dead code)
- Validar que os testes realmente cobrem o código

---

## 🧪 Testes Implementados

### Unitários
Testes unitários para:
- `extract.downloader` - Download de dados
- `extract.parser` - Parsing de arquivos CSV
- `extract.hasher` - Hashing de dados
- `upload.uploader` - Upload para S3
- `orchestrator` - Orquestração do pipeline

### End-to-End (E2E)
Testes completos do fluxo:
- Download → Parse → Upload → Verificação
- Validação de dados completos
- Testes com VCR/respx para mocks de API

---

## 🤝 Como me contratar

Este projeto demonstra minha capacidade de:

1. **Construir pipelines ETL** completos com qualidade garantida
2. **Implementar estratégia de testes** abrangente (unitários, e2e, fuzzing, mutação)
3. **Adotar novas tecnologias** (LLMs, opencode) para acelerar entregas
4. **Documentar e comunicar** valor técnico de forma clara
5. **Analisar qualidade de código** com ferramentas especializadas

### 📧 Entre em contato

- **LinkedIn**: [linkedin.com/in/kleber-yokota/](https://www.linkedin.com/in/kleber-yokota/)
- **GitHub**: [github.com/kleber-yokota](https://github.com/kleber-yokota)

---

> "A inteligência artificial não substitui engenheiros de dados, mas engenheiros que usam IA substituem os que não usam."

---

## 💡 Lições Aprendidas

### 🤖 LLMs como Aceleradores de Desenvolvimento

Percebi que **LLMs são extremamente úteis** para:

- **Escrever código** - Geração rápida de boilerplate, funções repetitivas
- **Produzir código** - Implementação completa de features com prompts bem estruturados
- **Análise de código** - Verificar se a ideia funciona antes de implementar

### 🔄 Git como Checkpoint de Segurança

Durante os **testes de mutação**, percebi que:

- O **git é um ótimo checkpoint** quando o código está bom
- Quando entramos nos testes de mutação, identificamos **o que precisa ser arrumado**
- **Momento delicado**: quando perdemos o que fizemos durante refatoração
- **Solução**: Commits frequentes antes de testes pesados salvam o dia

### 🛡️ Testes E2E: Segurança para Refatorar

Os **testes end-to-end** dão segurança porque:

- Validam se o **processo completo funciona**
- Cobrem **alguns caminhos críticos** do fluxo
- Permitem refatorar com **confiança total**
- Detectam regressões antes de chegar em produção

### 🧪 Emulação e Qualidade de Código

A **emulação (fuzzing)** agrega muito na qualidade:

- Encontra **bugs que testes manuais não descobrem**
- Valida **edge cases** inesperados
- Garante que o código lida com **inputs malformados**
- É essencial para **código de produção**

### 🚀 CI/CD: Reflexão sobre Qualidade

O **CI/CD precisa refletir sobre isso**:

- Pipeline deve rodar **todos os testes** (unitários, E2E, fuzz, mutação)
- **Feedback rápido** é crucial para manter qualidade
- **Automatizar tudo** que pode ser automatizado
- **Qualidade não é opcional** - é requisito para deploy

---

**Feito com ❤️ e 🤖 usando opencode + Qwen 3.5 9B**

*Objetivo: Criar agents inteligentes para extrair o máximo valor de LLMs em projetos de engenharia de dados*
