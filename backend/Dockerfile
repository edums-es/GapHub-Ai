FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código da aplicação
COPY . .

# CORREÇÃO: Usa printf para garantir newline real no entrypoint script
# (echo com \n em sh não cria newline real em todos os sistemas)
RUN printf '#!/bin/sh\npython db/init.py\nuvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}\n' > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

CMD ["/entrypoint.sh"]
