# O'quv Markaz Boshqaruv Tizimi — Backend va VPS'ga joylashtirish

Bu papkada tizimning Python (FastAPI) backend qismi joylashgan. U barcha
ma'lumotlarni (o'quvchilar, to'lovlar, o'qituvchilar, guruhlar va h.k.)
PostgreSQL bazasida saqlaydi.

> **v6.0 yangilanishi haqida eslatma:** bu versiyada "Hodimlar oyligi"
> (o'qituvchilarga ulush ajratish), o'qituvchilar uchun shaxsiy login/
> kabinet, "Jami o'quvchilar" ro'yxati va to'lov turi (naxt/click) kabi
> yangi imkoniyatlar qo'shildi. Bular uchun bazaga bir nechta yangi
> ustun/jadval kerak. Backend ishga tushganda (`on_startup`) bu
> ustunlarni **avtomatik va xavfsiz tarzda** (`ADD COLUMN IF NOT EXISTS`)
> qo'shib qo'yadi — eski ma'lumotlaringiz (o'quvchilar, to'lovlar va h.k.)
> hech qanday qo'shimcha amalsiz saqlanib qoladi. Shunchaki konteynerni
> qayta ishga tushirish (`docker compose up -d --build`) yetarli.

Frontend (brauzerda ochiladigan sahifa) alohida `.html` fayl bo'lib, u shu
backend'ga internet orqali (`fetch`) so'rov yuboradi.

---

## 1. Talablar

- Bitta VPS server (Ubuntu 22.04/24.04 tavsiya etiladi) — DigitalOcean,
  Timeweb, Beget, Hetzner va h.k. istalgani mos keladi. Kichik markaz uchun
  1 CPU / 1-2 GB RAM yetarli.
- Domen nomi (ixtiyoriy, lekin tavsiya etiladi — HTTPS uchun kerak bo'ladi).
- Docker o'rnatilgan bo'lishi (eng oson yo'l) YOKI Python 3.11+ va
  PostgreSQL to'g'ridan-to'g'ri o'rnatilgan bo'lishi.

Quyida ikkita yo'l ko'rsatilgan: **A) Docker bilan (tavsiya etiladi, eng
oson)** va **B) Docker'siz, qo'lda o'rnatish**.

---

## A) Docker bilan joylashtirish (tavsiya etiladi)

### 1-qadam: Serverga ulaning va Docker o'rnating

```bash
ssh root@SIZNING_SERVER_IP

# Docker va docker-compose plugin o'rnatish (Ubuntu uchun rasmiy skript):
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
```

### 2-qadam: Loyihani serverga yuklang

Bu papkani (backend) va frontend faylini serverga ko'chiring, masalan `scp`
orqali kompyuteringizdan:

```bash
# O'z kompyuteringizda (Windows'da Git Bash yoki PowerShell'dan ham ishlaydi):
scp -r backend root@SIZNING_SERVER_IP:/root/oquv-markaz-backend
scp oquv_markaz_v5_api.html root@SIZNING_SERVER_IP:/root/oquv-markaz-backend/frontend/index.html
```

(`frontend` papkasini serverda oldindan yaratib qo'ying: `mkdir -p
/root/oquv-markaz-backend/frontend`)

### 3-qadam: `.env` faylini sozlang

```bash
cd /root/oquv-markaz-backend
cp .env.example .env
nano .env
```

Albatta quyidagilarni o'zgartiring:
- `JWT_SECRET` — uzun, tasodifiy qator (generatsiya qilish uchun:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`)
- `POSTGRES_PASSWORD` (docker-compose.yml orqali o'qiladi, `.env`'ga
  qo'shing: `POSTGRES_PASSWORD=...`)
- `INITIAL_RAHBAR_PASSWORD`, `INITIAL_ADMIN_PASSWORD`,
  `INITIAL_SECRET_PASSWORD` — standart parollarni albatta o'zgartiring!
- `CORS_ORIGINS` — agar frontend backend bilan bir xil domenda (shu
  docker-compose orqali) ishlaydigan bo'lsa, `*` qoldirsa ham bo'ladi.

### 4-qadam: Ishga tushiring

```bash
docker compose --env-file .env up -d --build
```

Bir necha soniyadan keyin:
- Backend: `http://SIZNING_SERVER_IP:8000/api/health` — `{"status":"ok"}`
  qaytarishi kerak.
- Frontend: `http://SIZNING_SERVER_IP` — login sahifasi ochilishi kerak.

Standart login (`.env`'da o'zgartirmagan bo'lsangiz):
- Rahbar: `rahbar` / `rahbar123`
- Admin: `admin` / `admin123`

**Kirgandan so'ng darhol Sozlamalar bo'limidan login/parollarni va maxfiy
parolni o'zgartiring!**

### 5-qadam (tavsiya): HTTPS o'rnatish

Agar domeningiz bo'lsa, `nginx-frontend.conf` o'rniga to'g'ridan-to'g'ri
serverdagi asosiy Nginx + Certbot orqali HTTPS sozlashingiz mumkin. Eng
oson yo'l — Docker'dagi `frontend` xizmatini o'chirib, asosiy tizim
Nginx'ini domen bilan sozlash va uni backend konteyneriga (`localhost:8000`)
proksi qilish, so'ng `certbot --nginx` orqali sertifikat olish.

---

## B) Docker'siz, qo'lda o'rnatish

### 1. PostgreSQL o'rnatish

```bash
apt update && apt install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER oquv_user WITH PASSWORD 'kuchli_parol';"
sudo -u postgres psql -c "CREATE DATABASE oquv_markaz OWNER oquv_user;"
```

### 2. Python muhitini tayyorlash

```bash
apt install -y python3.11 python3.11-venv
cd /root/oquv-markaz-backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. `.env` faylini sozlang (yuqoridagi A-qism 3-qadamiga qarang), lekin
`DATABASE_URL`'da `db` o'rniga `localhost` yozing:

```
DATABASE_URL=postgresql://oquv_user:kuchli_parol@localhost:5432/oquv_markaz
```

### 4. Backend'ni systemd xizmati sifatida ishga tushiring

`/etc/systemd/system/oquv-backend.service` faylini yarating:

```ini
[Unit]
Description=Oquv Markaz Backend
After=network.target postgresql.service

[Service]
User=root
WorkingDirectory=/root/oquv-markaz-backend
EnvironmentFile=/root/oquv-markaz-backend/.env
ExecStart=/root/oquv-markaz-backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now oquv-backend
systemctl status oquv-backend
```

### 5. Nginx bilan frontend va backendni bitta domenga ulash

```bash
apt install -y nginx
```

`/etc/nginx/sites-available/oquv-markaz`:

```nginx
server {
    listen 80;
    server_name sizning-domeningiz.uz;

    root /root/oquv-markaz-backend/frontend;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/oquv-markaz /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# HTTPS uchun:
apt install -y certbot python3-certbot-nginx
certbot --nginx -d sizning-domeningiz.uz
```

---

## Frontend faylini qayerga qo'yish kerak?

`oquv_markaz_v5_api.html` faylini serverdagi `frontend/index.html` sifatida
joylashtiring (nomini index.html deb o'zgartiring). Fayl ichida yuqorida
`const API_BASE = window.API_BASE_URL || '/api';` qatori bor — bu, agar
frontend backend bilan **bir xil domenda** (yuqoridagi nginx sxemasi kabi)
joylashtirilgan bo'lsa, hech narsa o'zgartirmasdan ishlayveradi.

Agar frontend butunlay boshqa domenda (masalan Netlify'da) joylashtirilib,
backend boshqa serverda bo'lsa, `index.html` faylining `<head>` qismiga shu
qatorni qo'shing (backend manzilingizga moslab):

```html
<script>
  window.API_BASE_URL = 'https://api.sizningdomeningiz.uz/api';
</script>
```

va uni `<script src="...xlsx...">` qatoridan OLDIN joylashtiring.

---

## Muhim xavfsizlik eslatmalari

1. `.env` faylidagi `JWT_SECRET`ni albatta o'zgartiring — bu token
   (login sessiyasi) imzolash uchun ishlatiladi.
2. Standart parollarni (`rahbar123`, `admin123`, `maxfiy2026`) birinchi
   kirishdayoq albatta o'zgartiring.
3. PostgreSQL parolini kuchli qiling va uni hech kimga bermang.
4. Muntazam zaxira nusxa oling: tizimning "Hisobotlar → Zaxira nusxa"
   tugmasi orqali JSON fayl yuklab olinadi. Bundan tashqari, serverda
   PostgreSQL'ning o'zini ham davriy zaxiralash tavsiya etiladi:

   ```bash
   docker exec -t <db_container_nomi> pg_dump -U oquv_user oquv_markaz > backup_$(date +%F).sql
   ```

5. Agar bir nechta VPS/domen bilan ishlasangiz, `.env`dagi
   `CORS_ORIGINS`ni faqat kerakli domenlar bilan cheklang (`*` xavfsiz
   emas, ishlab chiqarishda aniq domenlarni yozing).

---

## API hujjatlari

Backend ishga tushgandan so'ng, quyidagi manzilda barcha API
endpoint'larining avtomatik hujjatini (Swagger) ko'rishingiz mumkin:

```
http://SIZNING_SERVER_IP:8000/docs
```

(Ishlab chiqarishda bu manzilni tashqi dunyodan yopib qo'yish tavsiya
etiladi — nginx orqali faqat `/api/` yo'lini oching, `/docs`ni emas.)
