FROM node:22-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json ./
RUN npm install --omit=dev

COPY server.js ./

ENV PORT=3000
ENV BAILEYS_AUTH_DIR=/data/auth

EXPOSE 3000

CMD ["npm", "start"]
