
## Публикация на домене
Смотри подробности в `infra/README.md`.

Кратко:
1) DNS A: realestate.ourdocs.org → <IP VPS>
2) Nginx + Certbot, применить `infra/nginx/conf.d/realestate.conf`
3) Metabase: https://realestate.ourdocs.org/
4) Prefect:  https://realestate.ourdocs.org/prefect/
