# Taxi Data ETL

Projeto de aprendizado de engenharia de dados utilizando modelos de LLM para acelerar o processo de desenvolvimento.

## 🚀 Objetivo

Aprender como construir projetos de engenharia de dados utilizando **opencode** com **Qwen 3.5 9B** para acelerar o desenvolvimento de pipelines de dados.

## 📁 Estrutura do Projeto

```
.
├── src/
│   ├── extract/          # Extração de dados
│   ├── transform/        # Transformação de dados
│   └── load/             # Carregamento de dados
├── config/               # Configurações
├── scripts/              # Scripts utilitários
└── tests/                # Testes
```

## 🛠️ Tecnologias

- **opencode** - CLI para assistência de codificação inteligente
- **Qwen 3.5 9B** - Modelo de linguagem para geração e revisão de código
- **Python** - Linguagem principal
- **AWS S3** - Armazenamento de dados
- **Apache Spark** - Processamento de dados

## 📊 Dados

Utiliza dados do **Yellow/Taxi NYC** para:
- Treinamento de pipelines de ETL
- Validação de qualidade de dados
- Testes de transformação

## 🎯 O que está sendo feito

### Atual Pipeline
- Decomposição de pipelines complexos em tarefas menores
- Orquestração de jobs com dependências
- Tratamento de erros e retry logic
- Monitoramento e logging

### Melhorias
- Otimização de custos com S3
- Paralelização de jobs
- Cache de resultados
- Documentação automática

## 🚦 Status

- [ ] Pipeline de extração
- [ ] Pipeline de transformação
- [ ] Pipeline de carregamento
- [ ] Orquestração
- [ ] Monitoramento

## 📝 Como rodar

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar pipeline
python src/pipeline.py
```

## 🤝 Contribuição

Este é um projeto de aprendizado. Contribuições são bem-vindas!

## 📄 Licença

MIT License
