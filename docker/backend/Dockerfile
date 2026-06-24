FROM nginx:alpine

ARG CUSTOMER
ARG ENVIRONMENT

COPY index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN sed -i \
  -e "s/\${CUSTOMER}/$CUSTOMER/g" \
  -e "s/\${ENVIRONMENT}/$ENVIRONMENT/g" \
  /usr/share/nginx/html/index.html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
