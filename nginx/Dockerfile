FROM nginx:1.25-alpine

# Удаляем дефолтную конфигурацию
RUN rm /etc/nginx/conf.d/default.conf

# Копируем конфиг для разработки
COPY default.dev.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
