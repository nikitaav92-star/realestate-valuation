## Детализированный план реализации для Cursor AI

Ниже — более мелкая декомпозиция проекта: каждый шаг занимает 5–15 минут, имеет осязаемый артефакт и проверку.

| Фаза | Шаг | Что делаем | Команда/действие | Проверка результата |
| --- | --- | --- | --- | --- |
| **F0. Подготовка** | F0.1 | Создаём папку , включаем git | Reinitialized existing Git repository in /opt/realestate/.git/ |  пустой, директория создана |
|  | F0.2 | Фиксируем техническое задание | Скопировать этот README в  | Файл существует,  показывает добавление |
|  | F0.3 | Проверяем Docker/Compose | Docker version 28.5.0, build 887030f, Docker Compose version v2.40.0 | Команды завершаются без ошибок |
| **F1. Инфраструктура** | F1.1 | Создаём базовую структуру каталогов |  | antminer_autoreboot.sh
antminer_cookie_test.txt
antminer_cookie.txt
antminer_fans.sh
antminer_observer.log
antminer_observer.log.1758302647
antminer_observer.log.1758302896
antminer_observer.pid
antminer_observer.sh
antminer_observer.sh.bak
antminer_rebooter.log
antminer_rebooter.sh
antminer_status_sample.html
antminer_watchdog_light.sh
antminer_watchdog.log
backup_vpn.sh
client1.conf
client1-final.conf
client1-fixed.conf
client1.png
_cookie_test.txt
db
disable-nftables-rollback.sh
Downloads
etl
fans.log
firewall-backup-2025-09-05_151536
hashsentry_bot.py
manual_status.html
_miner_status.html
Nikita_iPhone.ovpn
Nikita_Mac.ovpn
Nikita.ovpn
Ola_Honor.ovpn
Ola_iPhone.ovpn
Ola_Iphone.ovpn
Ola.ovpn
openvpnas_backup_20250905-100016
openvpn-v2-profiles
openvpn-v3-profiles
ops-starter-kit
ovpn-clients
prepare_qr_and_scp.sh
provisioner-backup-2025-09-03_08-27-16.tgz
provisioner_snapshot_2025-09-03_08-12-56
provisioner_snapshot_2025-09-03_08-15-47
provisioner_snapshot_2025-09-03_08-21-25
provisioner_snapshot_2025-09-03_08-27-16
reports
restore_report.txt
Roads.ovpn
Roads_v2.ovpn
Roads_yandex.ovpn
scripts
setup_gptagent.sh
setup_zyxel_openvpn.sh
ss_audit.sh
vpn_backups
wg24_auto.sh
wg_autosetup.sh
wg_client_diag.sh
wg-clients
wg-clients_wg0
wg_fix_wg0_input.sh
wg_ipv4_only.sh
wg_mac_quick_check.sh
wg_server_diag.sh
zyxel-client
zyxel-client.tar.gz
zyxel-inline.ovpn
Никита Айфон.ovpn
Никита Мак.ovpn
Оля Honor.ovpn
Оля Айфон.ovpn отображает созданные директории |
|  | F1.2 | Создаём  | как в промте 1 |  совпадает с шаблоном |
|  | F1.3 | Создаём  и  | как в промте 1 | .
..
antminer_autoreboot.sh
antminer_cookie_test.txt
antminer_cookie.txt
antminer_fans.sh
antminer_observer.log
antminer_observer.log.1758302647
antminer_observer.log.1758302896
antminer_observer.pid
antminer_observer.sh
antminer_observer.sh.bak
antminer_rebooter.log
antminer_rebooter.sh
.antminer_state
antminer_status_sample.html
antminer_watchdog_light.sh
antminer_watchdog.log
backup_vpn.sh
.bash_history
.bash_history-90768.tmp
.bashrc
.cache
client1.conf
client1-final.conf
client1-fixed.conf
client1.png
.config
_cookie_test.txt
.cursor
.cursor-server
db
disable-nftables-rollback.sh
Downloads
etl
fans.log
firewall-backup-2025-09-05_151536
.gitconfig
.hashsentry
hashsentry_bot.py
.lesshst
.local
manual_status.html
_miner_status.html
Nikita_iPhone.ovpn
Nikita_Mac.ovpn
Nikita.ovpn
Ola_Honor.ovpn
Ola_iPhone.ovpn
Ola_Iphone.ovpn
Ola.ovpn
openvpnas_backup_20250905-100016
openvpn-v2-profiles
openvpn-v3-profiles
ops-starter-kit
ovpn-clients
prepare_qr_and_scp.sh
.profile
provisioner-backup-2025-09-03_08-27-16.tgz
provisioner_snapshot_2025-09-03_08-12-56
provisioner_snapshot_2025-09-03_08-15-47
provisioner_snapshot_2025-09-03_08-21-25
provisioner_snapshot_2025-09-03_08-27-16
reports
restore_report.txt
Roads.ovpn
Roads_v2.ovpn
Roads_yandex.ovpn
scripts
setup_gptagent.sh
setup_zyxel_openvpn.sh
ss_audit.sh
.ssh
vpn_backups
wg24_auto.sh
wg_autosetup.sh
wg_client_diag.sh
wg-clients
wg-clients_wg0
.wget-hsts
wg_fix_wg0_input.sh
wg_ipv4_only.sh
wg_mac_quick_check.sh
wg_server_diag.sh
zyxel-client
zyxel-client.tar.gz
zyxel-inline.ovpn
Никита Айфон.ovpn
Никита Мак.ovpn
Оля Honor.ovpn
Оля Айфон.ovpn показывает файлы,  подтверждает содержимое |
|  | F1.4 | Пишем  и  | как в промте 1 |  после применения показывает таблицы |
|  | F1.5 | Поднимаем Compose |  |  все контейнеры  |
|  | F1.6 | Применяем схему |  |  возвращает  |
| **F2. Python окружение** | F2.1 | Создаём  | как в промте 2 |  совпадает |
|  | F2.2 | Разворачиваем venv |  |  указывает на  |
|  | F2.3 | Устанавливаем зависимости |  | Package               Version
--------------------- --------------
anyio                 4.10.0
arrow                 1.2.3
attrs                 23.2.0
Automat               22.10.0
bcc                   0.29.1
bcrypt                3.2.2
beautifulsoup4        4.12.3
blinker               1.7.0
boto3                 1.34.46
botocore              1.34.46
certifi               2023.11.17
cffi                  1.16.0
chardet               5.2.0
click                 8.1.6
colorama              0.4.6
command-not-found     0.3
configobj             5.0.8
constantly            23.10.4
cryptography          41.0.7
cssselect             1.2.0
dbus-python           1.3.2
defusedxml            0.7.1
distro                1.9.0
distro-info           1.7+build1
getmail6              6.18.13
h11                   0.16.0
html5lib              1.1
httpcore              1.0.9
httplib2              0.20.4
httpx                 0.25.2
hyperlink             21.0.0
idna                  3.6
incremental           22.10.0
isodate               0.6.1
jmespath              1.0.1
launchpadlib          1.11.0
lazr.restfulclient    0.14.6
lazr.uri              1.0.6
ldap3                 2.9.1
lxml                  5.2.1
netaddr               0.8.0
netifaces             0.11.0
oauthlib              3.2.2
packaging             24.0
pexpect               4.9.0
pip                   24.0
ply                   3.11
ptyprocess            0.7.0
pyasn1                0.4.8
pyasn1-modules        0.2.8
pycparser             2.21
PyGObject             3.48.2
PyHamcrest            2.1.0
PyJWT                 2.7.0
pyOpenSSL             23.2.0
pyparsing             3.1.1
pyserial              3.5
python-apt            2.7.7+ubuntu5
python-dateutil       2.8.2
python-debian         0.1.49+ubuntu2
python-magic          0.4.27
python-telegram-bot   20.6
python3-saml          1.12.0
PyYAML                6.0.1
requests              2.31.0
s3transfer            0.10.1
service-identity      24.1.0
setuptools            68.1.2
six                   1.16.0
sniffio               1.3.1
sos                   4.8.2
soupsieve             2.5
speedtest-cli         2.1.3
ssh-import-id         5.11
systemd-python        235
Twisted               24.3.0
typing_extensions     4.10.0
ubuntu-drivers-common 0.0.0
ubuntu-pro-client     8001
urllib3               2.0.7
wadllib               1.3.6
webencodings          0.5.1
wheel                 0.42.0
xkit                  0.0.0
xmlsec                1.3.13
zope.interface        6.1 содержит требуемые пакеты |
|  | F2.4 | Создаём  | как в промте 2 |  без ошибок |
|  | F2.5 | Создаём  | как в промте 2 |  без ошибок |
|  | F2.6 | Выполняем тестовую вставку | сценарий из промта 2 | В stdout «OK», в БД  |
| **F3. Сбор данных** | F3.1 | Настраиваем базовый payload | создать  |  (при наличии) проходит |
|  | F3.2 | Реализуем  | как в промте 3 |  |
|  | F3.3 | Реализуем  | как в промте 3 | Временный тест  |
|  | F3.4 | Реализуем  | как в промте 3 |  выводит команды |
|  | F3.5 | Делаем пробный  | команда из промта 3 | stderr содержит  или фиксируем «Не могу подтвердить это» + JSON |
|  | F3.6 | Прогоняем  | конвейер из промта 3 |  увеличился, без дублей |
| **F4. Оркестрация** | F4.1 | Создаём  | как в промте 4 |  |
|  | F4.2 | Пишем SQL-репорты |  |  без ошибок |
|  | F4.3 | Запускаем  | скрипт из промта 4 | Prefect лог без исключений |
|  | F4.4 | Проверяем деактивацию |  | Список соответствует ожиданию |
| **F5. Витрины/фронтенд** | F5.1 | Настраиваем Metabase | зайти на  | Создано подключение к Postgres |
|  | F5.2 | Создаём карточки DOM/₽/падения | Через UI Metabase | Скриншоты карточек сохранены |
|  | F5.3 | Поднимаем внешний API (если нужно) | следовать разделу 11 | Endpoint  возвращает JSON |
|  | F5.4 | Разворачиваем фронтенд на своём хостинге | Next.js/SSG по разделу 11 | Публичная страница доступна, lighthouse ≥80 |
| **F6. Контроль качества** | F6.1 | Прогоняем чек-лист из раздела 6 | ручной контроль | Все пункты отмечены |
|  | F6.2 | Ведём журнал багов |  + issues в git | У каждой записи есть дата, статус, ссылка на PR |
|  | F6.3 | Настраиваем автоматический бэкап |  + cron | В  появляется файл |

### Процесс фикса багов и контроль ошибок

1. **Детектор:** после каждого шага фиксируем / и SQL-снимки (). Ошибка → сразу логируем в .
2. **Реакция:** создаём git-ветку  и выполняем минимальный фикс; добавляем тест или SQL-проверку, которая ловит регрессию.
3. **Проверка:** повторяем только те шаги, которые затронуты фиксом, плюс smoke-тест  и .
4. **Документация:** обновляем разделы README/blueprint, если поведение изменилось (например, новый столбец или флаг).
5. **Автоматизация контроля:** по мере готовности добавляем , , интегрируем в CI Cursor/Devbox (опционально GitHub Actions).

> Советы: держите размер шага маленьким — один логический файл или таблица. Каждый завершённый шаг фиксируйте отдельным коммитом, чтобы упростить откат и ревью.
