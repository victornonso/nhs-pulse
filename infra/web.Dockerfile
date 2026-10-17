FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
ARG API_INTERNAL_URL=http://api:8020
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN npm run build
FROM node:24-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3020
ENV PORT=3020 HOSTNAME=0.0.0.0
CMD ["node","server.js"]
