FROM node:20-alpine

WORKDIR /app

# Install dependencies for website separately
COPY website/package*.json ./website/
RUN cd website && npm install

# Install dependencies for backoffice separately
COPY backoffice/package*.json ./backoffice/
RUN cd backoffice && npm install

COPY . .

RUN chmod +x /app/start.sh

EXPOSE 3000 3001

CMD ["./start.sh"]
