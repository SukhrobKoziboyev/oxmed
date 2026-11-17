# OXMED — O'quv markaz boshqaruv tizimi (OLMOS XATAMOV maktabi)

> Bu fayl yangi Claude Code sessiyasi uchun: loyiha nima, nimalar qilindi, hozirgi holat va keyingi vazifalar.
> Foydalanuvchi: **Sukhrob** (Toshkentda). Tizim Qashqadaryodagi o'quv markazga (OLMOS XATAMOV maktabi) masofadan topshiriladi.
> **Javoblarni o'zbek tilida yozing.** Foydalanuvchi terminalni yaxshi bilmaydi — buyruqlarni aniq, qaysi tabda yozilishini aytib, bittalab bering.

---

## 1. Loyiha tuzilishi (Mac: `~/Desktop/python/oxmed`)

```
oxmed/
├── CLAUDE.md                 ← shu fayl
├── frontend/
│   ├── index.html            ← BUTUN frontend bitta faylda (HTML+CSS+JS, ~516 KB). Joriy versiya: Pro 13.34
│   ├── logo.png              ← OLMOS XATAMOV logosi (fon shaffof)
│   ├── manifest.json, sw.js  ← PWA (telefon/kompyuterga ilova qilib o'rnatish)
│   ├── icon-192.png, icon-512.png, icon-maskable-512.png, apple-touch-icon.png
│   └── robots.txt, sitemap.xml   ← Google uchun
├── backend/                  ← FastAPI + SQLAlchemy + PostgreSQL
│   ├── requirements.txt      ← (webauthn==2.5.2 qo'shilgan)
│   └── app/
│       ├── main.py           ← ishga tushganda yengil migratsiyalar (ALTER TABLE ... IF NOT EXISTS)
│       ├── models.py, schemas.py, auth.py, database.py, utils.py
│       ├── ledger.py         ← O'QITUVCHI BALANSI — YAGONA MANBA (pastga qarang)
│       └── routers/  auth, payments, salary, teacher_self, teachers, subjects,
│                     students, settings, recycle, backup, webauthn_auth
└── _backup_2026-11-11/       ← ishni boshlashdan oldingi asl nusxa (frontend + backend/app). Serverga YUKLANMAYDI.
```

## 2. Server (ahost VPS)

- IP: `185.196.215.247`, Ubuntu 24.04, domen: **oxmed.uz** (HTTPS bor). Kirish: `ssh root@185.196.215.247` (parolni Sukhrob biladi).
- **oxmed.uz quyidagicha ishlaydi (Docker EMAS!):**
  - Sahifa: tizim nginx'i → `/var/www/oxmed/index.html` (va boshqa statik fayllar `/var/www/oxmed/` da)
  - Backend: systemd xizmati **`oxatamov.service`** (uvicorn, port 8000), kod: `/var/www/oxmed/backend/app`, venv: `/var/www/oxmed/backend/venv`, sozlamalar: `/var/www/oxmed/backend/.env` (DATABASE_URL=postgresql://...)
  - nginx `/api/` ni 8000-portga yo'naltiradi.
- Shu serverda boshqa loyihalar ham bor — **ularga tegmang**: `/root/oquv-markaz-backend` (papka qoldi; uning Docker bazasi `oquv-markaz-backend_pgdata` 2026-11-14 tozalashda o'chib ketgan, ishlatilmayotgan edi), `/root/oxmed_new` (eski, ishlatilmaydi). **EduMarkaz (Docker, port 8001) 2026-11-14 Sukhrobning iltimosi bilan butunlay o'chirildi** (zaxira: `/root/edumarkaz_baza_zaxira_2026-11-14.sql.gz`, `/root/edumarkaz_papka_zaxira_2026-11-14.tgz`); Docker'da hech narsa qolmadi. **Lug'atim bot (`lugatim.service`, `/opt/lugatim`, port 3077) 2026-11-13 Sukhrobning iltimosi bilan butunlay o'chirildi** (kichik zaxira: `/root/lugatim_zaxira_2026-11-13.tgz`).
- **Server resurslari (2026-11-14, tozalashdan keyin):** 1 vCPU, RAM 961 MB (bo'sh ~457 MB), disk 8,7 GB (3,7 GB band, **5,0 GB bo'sh**). Serverda faqat OXMED ishlaydi. Docker, containerd, ModemManager, udisks2, fwupd **to'xtatilgan va o'chirilgan** (`systemctl disable`; kerak bo'lsa `systemctl enable --now docker`). Eski zaxiralar tozalangan — qoldi faqat: `index_eski_12_7/12_8.html`, `backend/app_zaxira_12_7/12_8`, `/root/oxmed_baza_zaxira_2026-11-14_v12_7/v12_8.sql`. `oquv_tiklash` (bo'sh) bazasi o'chirildi. **`/var/www/OXatamov` — /var/www/oxmed ga yorliq (symlink), nginx `sites-available/default` ishlatadi — O'CHIRMANG.** OXMED bazasi `oquv_markaz` ≈ 9 MB, `/var/www/oxmed` ≈ 150 MB. O'quvchi rasmlari/fayllar qo'shilsa — RAM 2 GB va disk 20–40 GB ga oshirish kerak bo'ladi.
- **Serverdagi zaxiralar (2026-11-11):** `/var/www/oxmed/backend/app_zaxira_7_5`, `/var/www/oxmed/index_eski_7.5.html`, `/var/www/oxmed/index_eski_7.0.html`, `/var/www/oxmed/index_eski_5.2v.html`, baza: `/root/oxmed_baza_zaxira_2026-11-11.sql`
- Google Search Console tasdiqlash fayli: `/var/www/oxmed/google6c6b60a10e79db12.html` — **O'CHIRMANG**.

### Yuklash (deploy) tartibi
Foydalanuvchida Terminal'da 2 ta tab bor: **server tabi** (`root@vm59608`) va **Mac tabi** (`MacBook-Pro-sukhrob`). `scp` doim Mac tabida, qolgan buyruqlar server tabida.

Faqat frontend o'zgarsa:
```bash
# Mac tabida:
scp ~/Desktop/python/oxmed/frontend/index.html root@185.196.215.247:/var/www/oxmed/index.html
# Server tabida:
chmod 644 /var/www/oxmed/index.html && md5sum /var/www/oxmed/index.html
```
Backend o'zgarsa (avval zaxira oling: `cp -r backend/app backend/app_zaxira_X` + `pg_dump`):
```bash
# Mac tabida (kerakli fayllar ro'yxatini moslang):
cd ~/Desktop/python/oxmed && tar czf - backend/app/ledger.py backend/app/routers/salary.py | ssh root@185.196.215.247 "cd /var/www/oxmed && tar xzf - && echo BACKEND YUKLANDI"
# Server tabida:
systemctl restart oxatamov && sleep 3 && systemctl is-active oxatamov && curl -s localhost:8000/api/health
```
(`tar: Ignoring unknown extended header keyword LIBARCHIVE...` ogohlantirishlari zararsiz.)
Yangi Python kutubxona kerak bo'lsa: `/var/www/oxmed/backend/venv/bin/pip install ...`
Orqaga qaytarish (eng oxirgi zaxiraga): `cd /var/www/oxmed && rm -rf backend/app && cp -r backend/app_zaxira_13_1 backend/app && cp index_eski_13_1.html index.html && systemctl restart oxatamov`

---

## 3. Qilingan ishlar (2026-11-11 / 12)

**Rollar:** "Markaz rahbari" (to'liq), "Administrator" (to'lov/o'quvchi), "O'qituvchi" (o'z kabineti).

1. **Summa kiritish** `2 500 000` ko'rinishida (input `.money-input`, `parseMoney()` / `formatMoney()`), barcha raqamlar bo'shliq bilan.
2. **"📑 Umumiy jadval"** (faqat rahbar) — boshliqning Excel jadvaliga o'xshash: to'lov × fanlar bo'yicha ulush × o'qituvchilar bo'yicha ulush × markazga qolgan; oy/tur/usul filtri, Excel export, to'lamaganlar ro'yxati, telefonda kartochka.
3. **Dizayn:** kompyuterda chap sidebar + KPI kartalar; telefonda ilova uslubi — to'q binafsha tepa panel, pastda "shisha" suzuvchi menyu (o'rtada 💰 To'lov tugmasi). "Eng faol yo'nalishlar" va Sozlamalardagi "Tizimni tozalash"/"Muhim eslatmalar" olib tashlangan. Statistika bo'limi ixcham kartalar bilan qayta qilingan. Logo hamma joyda.
4. **SEO:** sarlavha "OXMED — OLMOS XATAMOV maktabi", meta/OG/JSON-LD, robots.txt, sitemap.xml. Search Console tasdiqlangan, sitemap yuborilgan, indekslash so'ralgan (natija 1–3 hafta).
5. **PWA:** telefon (Android bir bosishda, iPhone — Ulashish → "На экран «Домой»") va kompyuter (Chrome/Edge ⊕, Mac Safari: Fayl → Dokka qo'shish) uchun o'rnatish tugmalari/ko'rsatmalar. sw.js hech narsani keshlamaydi → yangilanish o'zi tushadi.
6. **Hisob-kitob (ENG MUHIM — xato bo'lmasligi shart):**
   - `backend/app/ledger.py` — yagona manba. **Balans = ulushlar (PaymentAllocation) − berilgan oylik/avans + qaytarilgan pul.**
   - `teacher_payouts.kind`: `'payout'` (berildi, ayiriladi) | `'return'` (o'qituvchi qaytardi, qo'shiladi). Migratsiya `main.py` da.
   - Balans + → "Hozir olishingiz kerak bo'lgan summa"; − → "Hozir markazga berishingiz kerak bo'lgan summa".
   - Qarz ikki yo'l bilan yopiladi: (a) keyingi o'quvchi to'lovlaridagi ulush avtomatik qo'shiladi; (b) "↩️ Pul qaytardi" (faqat balans manfiy bo'lsa ko'rinadi, qarzdan ko'p kiritib bo'lmaydi). Eski yozuvlar o'chirilmaydi.
   - "📒 Hisob varag'i" — har bir yozuv + undan keyingi balans (`/api/salary/teacher/{id}/ledger`, o'qituvchi uchun `/api/teacher/ledger`). Server ketma-ket balans va SQL yig'indisini solishtiradi (assert).
   - Bosh sahifadagi "Kassadagi sof summa" = tushum − (berilgan − qaytarilgan).
7. **O'qituvchi kabineti:** pastki menyu (Asosiy / O'quvchilar / Hisob / Profil), qarz ogohlantirishi, o'quvchilar qidiruv+filtr, 3 mavzu (Yorug'/Tungi/Shaffof), "Chiqish" qizil.
8. **Barmoq izi / Face ID (WebAuthn passkey):** `routers/webauthn_auth.py`, jadvallar `webauthn_credentials`, `auth_challenges`. RP_ID default `oxmed.uz` (env: `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGINS`). Parol bilan kirgandan keyin "Keyingi safar parolsiz kirasizmi?" taklifi; profil (rahbar/admin: tepadagi ism ustiga bosish; o'qituvchi: Profil) — qurilmalar ro'yxati/o'chirish.
9. **O'qituvchi parolini tiklash:** rahbar Sozlamalar → O'qituvchilar → "🔢 Tiklash kodi" → 6 xonali kod (30 daqiqa, 1 marta, 5 xatoda bekor, xeshlangan; jadval `password_reset_codes`). O'qituvchi: "Parolni unutdingizmi?" → "O'qituvchiman". Rahbar — avvalgidek maxfiy parol bilan.
10. **Telefon uchun ro'yxatlar (v7.8):** To'lovlar tarixi, Admin tarixi, Jami o'quvchilar (📞 qo'ng'iroq), O'qituvchilar va Fanlar (Sozlamalar) telefonda Telegram/iOS uslubidagi ro'yxat (`.m-only`), qatorga bosilsa pastdan amallar oynasi (`openActionSheet`). Kompyuter jadvallari `.d-only` da o'zgarmagan. Hook'lar `hookMobileLists()` da (asl funksiyalarni o'rab oladi). Excel orqali o'quvchi yuklash olib tashlangan. Internet uzilsa qizil banner.
11. Sozlamalar bo'limlari yig'iladigan (accordion) kartalar.

### Serverdagi holat
- Backend v7.7 (ledger, webauthn, reset-code) **yuklangan va ishlayapti** (`{"available":true}`), md5: ledger.py `1561fc9b…`, webauthn_auth.py `cbc87d17…`, models.py `6bb6a91b…`.
- Frontend: serverda v7.7 (`26eb4192…`). **Mac'dagi v7.8 (`f91deebd…`) HALI YUKLANMAGAN** bo'lishi mumkin — `md5sum /var/www/oxmed/index.html` bilan tekshiring.

---

### v7.9 (2026-11-12) — serverga YUKLANGAN (backend + frontend)
- **Umumiy jadval** kompyuterda to'liq ekran (sidebar qoladi, jadval qolgan balandlikni egallaydi — `fitBossTable()`, CSS `@media (min-width:769px)`).
- Jadval katagi bosilsa → tahrirlash oynasi (`openPaymentEditor(pid, focus)`, modal `#editModal`): summa, usul, oy, sana (oy/sana faqat rahbar), o'qituvchilar ulushi (qo'shish/o'zgartirish/olib tashlash, "⚡ Foiz bo'yicha"), "🗑️ To'lovni o'chirish". Ism katagi → `openStudentEditor`. "➕ To'lov qo'shish" → `openNewPaymentEditor`.
- To'lovlar tarixi / Admin tarixidagi "Tahrirlash" ham shu oynani ochadi (ulushlar bilan).
- Jami o'quvchilar: "✏️ Tahrirlash" (ism, familiya, telefon, sinf) — `PUT /api/students/{id}` (rahbar+admin); to'lovlardagi ism/telefon nusxasi ham yangilanadi, summalar/ulushlar tegilmaydi.
- `PUT /api/payments/{id}`: yangi maydonlar `allocations` (berilsa — ulushlar to'liq almashtiriladi, yig'indi ≤ summa), `month`, `date` (faqat rahbar). `allocations` berilmasa — eski xatti-harakat (mutanosib). `POST /api/payments`: ixtiyoriy `date` (rahbar), oy tekshiriladi.
- **Soat xatosi tuzatildi:** server UTC'da edi, `datetime.now()` 5 soat orqada yozardi. `utils.py`: `UZ_TZ` (UTC+5). API'dagi `date_str` (to'lov, payout, ledger) endi doim `timestamp`'dan Toshkent vaqtida hisoblanadi (`schemas._UzDateMixin`) — eski yozuvlar ham to'g'ri ko'rinadi, bazadagi ma'lumot o'zgartirilmaydi. O'quvchi `added_at` (utcnow) ham +5 bilan ko'rsatiladi.
- Sinov: lokal PostgreSQL'da 33 ta ssenariy (TZ=UTC bilan ham), brauzerda kompyuter + telefon ko'rinishi.
- Yuklanadigan backend fayllar: `utils.py schemas.py routers/payments.py routers/students.py routers/backup.py`. Mac zaxirasi: `_backup_2026-11-12_v7.8/`.

### v8.0 (2026-11-12) — faqat frontend
- Umumiy jadval: kompyuterda kirganda brauzer to'liq ekrani (Fullscreen API) o'zi yoqiladi (+ "⛶ To'liq ekran" tugmasi), tepa `.navbar` yashiriladi; "Sinf / Fan" va "Usuli" ustunlari olib tashlandi (Excel'da qoldi); o'qituvchi ustuni sarlavhasida ism va familiya ikki qatorda.
- "Qayta tiklash" kartalari `.rb-card` (oldin `menu-card` gridi tufayli yozuvlar ustma-ust tushardi).
- **Yangi versiya oynasi:** sahifa har 60 soniyada (va ilovaga qaytganda) `HEAD /index.html` qilib ETag/Last-Modified ni solishtiradi; o'zgarsa "Yangi versiya tayyor! → 🔄 Yangilash". Shuning uchun **har deploy'da faqat index.html ni yuklash kifoya** — ochiq turgan hamma qurilmada oyna chiqadi.
- Serverdagi zaxiralar (2026-11-12): `/root/oxmed_baza_zaxira_2026-11-12.sql`, `backend/app_zaxira_7_8`, `index_eski_2026-11-12.html`.

### v8.1 (2026-11-12) — faqat frontend
- To'lov kiritish: sinf (maktab), o'qituvchi va guruh (repetitor) **ixtiyoriy**. Qidiruv maydoniga ism/familiya yozilsa, pastda "Familiya Ism — sinf/fan" ro'yxati chiqadi (`filterPaymentStudents`, `getPaymentCandidateStudents`, `pickPaymentStudent`). Sinf tanlansa — shu sinf ichida, bo'lmasa — hammasidan.
- Qidiruv `normSearch/searchMatch`: bo'sh joy, katta-kichik harf, apostrof (o' oʻ o`) farqi yo'q, so'zlar istalgan tartibda, telefon raqami raqamlar bo'yicha. Jami o'quvchilar va To'lovlar tarixi qidiruvida ham.
- Bir o'quvchi bir nechta fanga to'lasa: "➕ O'qituvchi qo'shish", jonli yig'indi (`#paymentAllocSum`). Foiz bo'yicha taklif qilingan qator (`data-pct`) summa o'zgarsa moslanadi, qo'lda yozilgani o'zgarmaydi. O'qituvchisiz summa yoki yig'indi > summa bo'lsa saqlanmaydi. Ulushlar ataylab o'chirilsa `auto_split:false`.
- Telefonda o'rnatilgan ilova (standalone) rejimida tepadan tortib yangilash (`setupPullToRefresh`) — brauzer tabida o'zining yangilashi ishlaydi.
- Yangilash oynasi: v7.9 da tekshiruv kodi yo'q edi, shuning uchun v8.0 yuklanganda chiqmadi; v8.0+ ochiq turgan qurilmalarda chiqadi. Qo'shimcha `focus`/`pageshow` tekshiruvlari qo'shildi.

### v8.2 (2026-11-12) — backend `routers/students.py` + index.html
- O'quvchi qo'shishda repetitor uchun **guruh ixtiyoriy** (o'qituvchi majburiy). Guruhsiz o'quvchida `group_label = NULL`; frontend'da hamma joyda "Guruhsiz" deb ko'rsatiladi, statistika/Excel'da alohida "Guruhsiz" qatori bor. Guruh berilsa, u shu o'qituvchiniki bo'lishi tekshiriladi.
- v8.1 serverga yuklangan; "Yangilash" oynasi haqiqiy qurilmada ishlashi tasdiqlandi.

### v8.3 (2026-11-12) — faqat index.html (v8.2 serverda)
- O'quvchini o'chirish: tur, sinf, o'qituvchi, guruh — hammasi ixtiyoriy; ism/familiya bo'yicha qidiruv va pastdan ro'yxat (`filterDeleteStudents`, `pickDeleteStudent`). Umumiy filtr `studentsByFilters(typeId, classId, teacherId, groupId)` — to'lov kiritish ham shundan foydalanadi.
- O'qituvchi tanlanganda guruh ro'yxatida "— Guruhsiz o'quvchilar —" (`__none`) varianti bor (to'lov kiritish va o'chirishda) — `fixFilterGroupSelect`.

### v8.4 (2026-11-12) — XODIMLAR + yangilanish belgisi (backend 11 fayl + index.html + sw.js)
- **Xodimlar** (farrosh, oshpaz, direktor o'rinbosari...): `teachers` jadvalida `is_staff=TRUE`, `subject_id=NULL` (migratsiya: `ALTER COLUMN subject_id DROP NOT NULL` + `is_staff, position, monthly_salary, salary_start`). Login/parol kodi/barmoq izi/oylik berish (`/api/salary/payout`)/hisob varag'i o'qituvchilarniki bilan bir xil.
- Oylik hisoblanishi: yangi jadval `salary_accruals` (kind `monthly` — har oyga bitta, unique index; `extra` — bonus). `ledger.ensure_staff_accruals()` salary_start oyidan joriy oygacha yo'q oylarni yaratadi (joriy oy ham, oy boshida). Bekor qilingan oylik o'chirilmaydi, `amount=0` (qayta yaratilmasligi uchun). `ledger.teacher_totals`: total_allocated = ulushlar + hisoblangan oylik (o'qituvchilarda 0 → ularning hisobi o'zgarmaydi).
- API: `/api/staff` (GET/POST), `/api/staff/{id}` (PUT/DELETE), `/api/staff/{id}/ledger`, `/api/staff/{id}/accrual` (POST), `/api/staff/accrual/{aid}` (PUT/DELETE). Xodimlar `/api/teachers` va `/api/salary/overview` da chiqmaydi; xodimga o'quvchi/guruh/ulush biriktirib bo'lmaydi; zaxiradan tiklash va "tozalash" xodimlarni o'chirmaydi.
- Frontend: rahbar menyusida "👷 Xodimlar" (`staffSection`, `loadStaffSection`); kabinet `dash.is_staff` bo'lsa o'quvchilar qismi yashiriladi (`#teacherPortal[data-staff="1"]`).
- Yangilanish belgisi: yangi versiya topilsa — ilova belgisida 1 (`navigator.setAppBadge`), sarlavhada "(1)", ekranda "🔄 Yangilanish 1" tugmasi, ruxsat berilgan bo'lsa tizim bildirishnomasi (`sw.js` da `notificationclick`). Ruxsat bir marta so'raladi (`#notifAsk`). Eslatma: faqat ilova ochiq yoki fonda turganda ishlaydi (push-server yo'q).
- Sinov: `t84.py` — 33 ta ssenariy (TZ=UTC, eski bazada migratsiya bilan), o'qituvchilar balansi o'zgarmagani tasdiqlangan.

### v8.5 (2026-11-12) — O'QUVCHI QARZI (backend `routers/dues.py` + models/main/schemas/payments + index.html)
- Jadval `student_dues` (student_id, month, due_amount; unique (student_id, month); o'quvchi o'chsa CASCADE). **Qarz = max(0, due_amount − shu oy to'langan)** — o'quvchi qolganini to'lasa qarz o'zi kamayadi; o'qituvchi ulushiga ta'sir qilmaydi.
- `POST /api/payments` va `PUT /api/payments/{id}` da ixtiyoriy `debt` (qolgan qarz; 0 = yopish). `GET /api/dues` (qarzdorlar), `PUT /api/dues` {student_id, month, debt, note} (rahbar+admin).
- Frontend: to'lov formasida "🔴 Qarz qoldi" + hozirgi qarz ko'rsatkichi; Umumiy jadvalda "Qarz" ustuni (qizil, o'quvchi+oyning oxirgi to'lov qatorida), "🔴 Qarzlar" kartochkasi, "Qarzdorlar" ro'yxati, "🔴 Qarz kiritish" (`openDebtEditor`); tahrirlash oynasida qarz maydoni; Jami o'quvchilarda qizil belgi; Excel'da QARZ ustuni va "Qarzdorlar" varag'i.
- Eslatma: oylar yilsiz (to'lovlar kabi) — keyingi yilning shu oyi bilan aralashishi mumkin.
- v8.4 serverga yuklangan (2026-11-12). v8.5 uchun: models.py, main.py, schemas.py, routers/dues.py, routers/payments.py + index.html.

### v8.6 (2026-11-12) — models/main/schemas/students/recycle/backup + index.html
- Repetitor o'quvchi qo'shishda **o'qituvchi ham ixtiyoriy** (fan/o'qituvchi/guruh NULL; to'lovida avtomatik ulush yo'q). Frontend'da `repInfo()` — bo'sh bo'lsa "O'qituvchisiz".
- `students.phone2` (qo'shimcha telefon, ixtiyoriy): qo'shish, tahrirlash (`""` — o'chirish, berilmasa o'zgarmaydi), ro'yxatlar, qidiruv, qo'ng'iroq, zaxira/qayta tiklash.
- Namunalar (placeholder): "Sukhrob", "Koziboyev", "Sukhrob Koziboyev", "778776877" (Sukhrobning iltimosi bilan).

### v8.7 (2026-11-12) — TEZLIK + majburiy yangilash + PUSH (backend: main, models, routers/payments, routers/push.py, push_notify.py, requirements.txt + index.html + sw.js)
- **Tezlik:** Excel kutubxonasi (880 KB) endi faqat Excel tugmasi bosilganda yuklanadi (`loadXLSX()`, eksport funksiyalari o'raladi); Google shriftlari sahifani to'smaydi; ilova `window.onload` emas DOM tayyor bo'lishi bilan ishga tushadi; API javoblari gzip (`GZipMiddleware`); `/api/payments` ulushlarni bitta so'rovda oladi (`selectinload`); 7 ta so'rov parallel.
- **Keshdan darhol ochilish:** ma'lumotlar `localStorage['oxmed_data_cache_v1']` da (foydalanuvchi+rol bilan; chiqishda o'chadi); ochilganda darhol ko'rsatiladi, orqada `refreshAppData({silent:true})` yangilaydi (401/403 → logout). `sw.js` index.html ni keshdan beradi va orqada serverdagisi bilan solishtiradi (ETag) — o'zgargan bo'lsa sahifaga `oxmed-update` xabari + `/__oxmed_update` belgisi. `/api/` hech qachon keshlanmaydi.
- **Tortib yangilash** endi sahifani qayta yuklamaydi — `refreshAppData()` (o'qituvchi kabinetida ham, joriy tab saqlanadi).
- **Yangilash majburiy:** "Keyinroq" olib tashlandi, oyna yopilmaydi (`onAppUpdateFound`). HEAD tekshiruvi har 30 soniyada. "Yangilash" yangi index.html ni SW keshiga yozib, sahifani qayta ochadi; belgi (1) va eski bildirishnomalar tozalanadi.
- **Web Push:** `push_subscriptions` jadvali, `/api/push/key|subscribe|unsubscribe`. VAPID kalitlari serverda birinchi so'rovda `backend/vapid_keys.json` ga yaratiladi (**o'chirmang** — o'chsa hamma qayta obuna bo'lishi kerak; Mac'dagi lokal sinov kaliti serverga yuklanmaydi). Ruxsat berilgan qurilmalar avtomatik obuna bo'ladi (`ensurePushSubscription`). Ruxsat so'rash bir marta qayta chiqadi (`oxmed_notif_asked2`).
- **Har deploy'dan keyin (index.html yuklangach) serverda:** `cd /var/www/oxmed/backend && venv/bin/python -m app.push_notify "Pro 8.x"` — ilova yopiq bo'lsa ham bildirishnoma + belgida "1"; SW yangi versiyani oldindan keshga yuklaydi. (iPhone: faqat "Bosh ekranga qo'shilgan" ilovada, iOS 16.4+.)
- Sinov: `t87.py` (9), headless Chromium `pw87.py` (24: SW kesh, majburiy oyna, push, Excel, eskirgan token), t85/t86 qayta o'tdi.

### v8.8 (2026-11-12) — takroriy to'lov, Yo'qlama (qulf), xavfsizlik, animatsiyalar (backend: main, auth, security.py, schemas, routers/auth, routers/payments + index.html)
- **Takroriy to'lov:** `POST /api/payments` shu o'quvchi+oy uchun to'lov bo'lsa **409** `{code:'duplicate_month', payments:[{amount, method, date, added_by}], total}` qaytaradi; o'quvchi qatori `with_for_update()` bilan qulflanadi (ikki admin bir vaqtda kiritsa ham bittasi o'tadi). Frontend `postPaymentChecked()` → `askDuplicatePayment()` oynasi ("✋ Yo'q, kiritmayman" / "Ha, yana kiritaman" → `allow_duplicate:true`). To'lov kiritish va Umumiy jadvaldagi "➕ To'lov qo'shish" ikkalasida. Qism-qism to'lash (qarz) ham shu "Ha" orqali.
- **Yo'qlama:** menyuda qulflangan karta (`#menuAttendance`, `.menu-locked`), bosilsa `showLockedFeature()` — "200 $ to'lov qilishingiz kerak" + dasturchi telefoni. Bo'limning o'zi hali yo'q (`showSection('attendanceSection')` ushlab qolinadi).
- **Xavfsizlik:** login 5 xatodan keyin vaqtincha blok (1 daqiqadan 30 daqiqagacha oshib boradi), IP bo'yicha 20 ta; maxfiy parol 3 xatodan keyin 5 daqiqa+; o'qituvchi kodi IP bo'yicha. `.env` da JWT_SECRET bo'lmasa — `backend/jwt_secret.key` avtomatik yaratiladi (standart kalit bilan soxta token yasab bo'lmaydi; **o'chirmang**, o'chsa hamma qayta kiradi). JSON so'rovlarda `<` `>` taqiqlangan (parol maydonlaridan tashqari) — XSS oldini olish. `/api` javoblarida nosniff, X-Frame-Options DENY, no-store. `/docs` o'chirilgan (`ENABLE_DOCS=1` bilan yoqiladi). CORS standart: faqat oxmed.uz. Sahifa iframe ichida ochilmaydi.
- **Animatsiyalar:** bo'limlar va oynalar bosilgan joydan shaffof+xira → aniq bo'lib ochiladi (`oxOpen`, `oxPop`; telefonda pastdan prujina `oxSheet`); bosh sahifa kartalari ketma-ket; tugmalar bosilganda yengil botadi. `fill-mode: backwards` (tugagach transform qolmaydi). `prefers-reduced-motion` da o'chadi.
- Sinov: `t88.py` (16), `pw87.py` (24), t85 (allow_duplicate bilan), t86.

### v8.9 (2026-11-12) — admin tarixi, admin menyulari, SMS (Eskiz.uz) (backend: models, main, schemas, routers/payments, settings, recycle, sms.py + index.html)
- **Admin "📋 Mening to'lovlarim"** rahbarning "To'lovlar tarixi" bilan bir xil: oy tablari (+"Barchasi", sonlari bilan), qidiruv, binafsha statistika (soni, o'quvchilar, jami, naqd/click, bugun), jadval; telefonda `mPaymentSummary + mPaymentRows`. Rahbar tablari endi `#monthTabs` bilan cheklangan.
- **Admin menyusi:** "Hodimlar oyligi" yashirildi; "♻️ Qayta tiklash" ochildi — admin faqat o'quvchi/to'lovni ko'radi va tiklaydi (`require_staff`), "Butunlay o'chirish" va to'liq zaxira faqat rahbarga.
- **Tuzatildi:** qayta tiklangan to'lovda usul (click) va o'qituvchi ulushlari yo'qolardi — endi tiklanadi (o'chirilgan o'qituvchi bo'lsa teacher_id=NULL, nom saqlanadi).
- **SMS (Eskiz.uz):** `routers/sms.py`. Login FAQAT serverdagi `.env`: `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_FROM` (nik tasdiqlanguncha 4546). Token xotirada, 401 da qayta login. To'lov saqlangach `BackgroundTasks` bilan ota-onaga (o'quvchi telefoni) va rahbar raqamlariga shablon bo'yicha SMS; har biri `sms_logs` da. Sozlamalar: `settings.sms_enabled/sms_to_parent/sms_to_rahbar` (standart: o'chiq). API: `/api/sms/status|settings|test` (rahbar). Sozlamalar → SMS bo'limida holat/balans, kalitlar, sinov SMS, jurnal.
- Eskiz test rejimida faqat "Bu Eskiz dan test" boradi; haqiqiy matnlar Eskiz kabinetida shablon tasdiqlangach ketadi (tasdiqlanmasa jurnalda xato ko'rinadi).
- Sinov: `t89.py` (19, soxta Eskiz serveri bilan `mock_eskiz.py`), t85–t88.

### v9.0 (2026-11-12) — SMS bo'limi + admin tarixi tuzatildi (v8.9 bilan birga yuklanadi)
- **Admin "📋 To'lovlar tarixi"** endi HAMMA to'lovlarni ko'rsatadi (kim to'lagan) + "🙋 Men kiritganlar" filtri, "Kim kiritdi" ustuni. Tahrirlash — faqat o'zi kiritganlarini.
- **"✉️ SMS xabarlar" bo'limi** (`#smsSection`, rahbar + admin): 🔴 To'lamaganlar (oy/tur/qidiruv, ro'yxat checkbox bilan, "⏰ Eslatma" yoki "⚠️ Muddati o'tgan" shablon, `{ism} {familiya} {oy} {qarz} {sinf} {fan}`, namuna, belgi/SMS soni, bitta tugma) • 📢 E'lon (hammasi/maktab/repetitor) • 📊 Hisobot (ketdi/ketmadi/o'tkazildi, bugun, balans, "Muammolar va yechimlari" — `smsHint()`, yuborishlar progress bilan, jurnal filtrlari) • ⚙️ Sozlamalar (Eskiz holati, to'lov SMS kalitlari — faqat rahbar, sinov SMS).
- Backend: `sms_batches` jadvali, `sms_logs.batch_id/student_id`, `settings.sms_template_reminder|overdue|announce`. API (rahbar+admin): `GET/PUT /api/sms/templates`, `POST /api/sms/bulk` (orqada yuboradi, 30 daqiqa ichida ishlayotgan yuborish bo'lsa 409), `GET /api/sms/batches`, `GET /api/sms/logs?batch_id&status`. `/api/sms/status` va `/test` endi admin uchun ham; `/settings` — faqat rahbar.
- "To'lamagan" = shu oy to'lovi yo'q YOKI qarzi bor (`database.dues`). SMS o'quvchining asosiy telefoniga (`phone`) boradi.
- Sinov: `t90.py` (15), `t89.py` (19, yangilangan).
- Eskiz holati (2026-11-12, Safari'da ko'rildi): balans 3 645 so'm, "Test rejimida", shartnoma chiqarilgan; API kalit hali serverga kiritilmagan.
- **Eskiz (2026-11-13 kechasi):** NTM Didox'da ro'yxatdan o'tdi (Mac'da E-IMZO "ID Karta" ilovasi + `~/DSKEYS/*.pfx`; ko'prik 127.0.0.1:64443 ishlashi uchun E-IMZO oynasi ochiq turishi kerak, birinchi ulanishda E-IMZO'da "Ruxsat berish"). Shartnoma №2376-2026 Didox'da IMZOLANGAN. 300 000 so'm Sukhrobning kartasidan (Zoomrad → Rekvizitlar bo'yicha to'lov → Hisob raqamga) BEST INTERNET SOLUTION ga yuborildi, tiket+chek. Kutilmoqda: Eskiz test rejimidan chiqarishi. Keyin: "Mening matnlarim" shablonlari (lotin, qisqa — 160 belgi), SMS shlyuz kaliti → server .env, sinov SMS, to'lov SMS'larini yoqish. Nik keyinroq (max 11 belgi, taklif: O.XATAMOV); hozircha 4546 raqamidan.

### v9.1 (2026-11-12) — O'zbekiston bayrog'i dizayni, AI yordamchi (qulf), avtomatik push (backend: main, routers/push + index.html, manifest.json)
- **Dizayn (hamma uchun):** ranglar `--uz-blue #0099B5`, `--uz-green #1EB53A`, `--uz-red #CE1126` (CSS oxirida "v9.1: O'ZBEKISTON BAYROG'I USLUBI" bloki). Login — haqiqiy bayroq (oy + 12 yulduz SVG). Kompyuter: ko'k yon menyu, o'ng chetida bayroq lentasi, tepa panel ostida qizil-oq-qizil-yashil chiziq. Telefon: ko'k tepa panel pastida bayroq chiziqlari, pastki menyu to'q ko'k-yashil. Logo hamma joyda oq "tanga" ustida. O'qituvchi kabineti ham. theme-color `#0089a6`.
- **"Statistika" menyusi yashirildi** (kod qoldi), o'rniga **🤖 Sun'iy intellekt yordamchi** — qulflangan, 350 $ (`#menuAI`, `showLockedFeature('ai')`; telefon pastki menyusida "AI"). O'qituvchi/xodim kabinetida ham AI bloki (`.tp-ai-lock`). `LOCKED_FEATURES` — Yo'qlama (200 $) va AI (350 $).
- **Qulflangan kartalar** premium uslubda: to'q fon, oltin chegara, ikonkada oltin qulf, matn ostida "🔒 Yopiq • 200 $" (endi sarlavha ustiga tushmaydi); telefonda to'liq kenglikda.
- **Avtomatik push:** backend `start_update_watcher()` har 15 soniyada index.html xeshini tekshiradi; o'zgarsa (5 s barqaror) — hamma obunachilarga push (`Urgency: high`, TTL 7 kun — oflayn qurilmaga ulanganda boradi). Holat `backend/.last_index_hash`, bitta jarayon `fcntl` qulfi bilan. **Endi `push_notify` ni qo'lda ishlatish shart emas.** O'chirish: `PUSH_WATCH=0`. Ochiq sahifalar HEAD tekshiruvi 15 s.

### v9.2 (2026-11-12) — faqat frontend (index.html, manifest.json, sw.js + yangi belgilar)
- Sukhrob: bayroq **faqat tashqi tomon** uchun edi — ichki ranglar v9.0 dagidek qaytarildi. Bayroq qoldi: **login foni** va **ilova belgisi**.
- Yangi belgilar (bayroq foni + oy/12 yulduz + markazda logo): `icon-uz-192.png`, `icon-uz-512.png`, `icon-uz-maskable-512.png` (yulduzsiz, xavfsiz zona), `apple-touch-icon-uz.png`, `favicon-uz.png` (brauzer tabi). Yasash skripti: scratchpad `mkicon.py` (PIL, `logo.png` dan). Fayl nomi yangi — telefonlar keshini chetlab o'tish uchun. iPhone'da belgi faqat ilovani bosh ekrandan o'chirib qayta qo'shganda yangilanadi.
- PRO kartalar (Yo'qlama, Sun'iy intellekt yordamchi): tavsif matni olib tashlandi — faqat nom + "🔒 Yopiq • narx".
- **🌙 Tun / ☀️ Kun** tugmasi (kompyuterda, "Markaz rahbari" yonida, `#uiModeBtn`, `toggleUiMode()`): `html[data-ui="dark"]`, `localStorage.oxmed_ui_mode`; sahifa ochilishida `<head>` dagi skript darhol qo'llaydi.

### v9.3 (2026-11-13) — faqat index.html: TELEFON "Soliq" uslubida
- "Hodimlar" → **"Xodimlar"** (sahifadagi hamma joyda; backend'da faqat izohlarda qoldi).
- Telefon (≤768px, yorug' rejim) uchun CSS bloki "v9.3: TELEFON — Soliq ilovasi uslubida" (`--m-*` o'zgaruvchilar, `html:not([data-ui="dark"])` bilan): oq tepa panel; bosh sahifada markazda katta "Kassadagi sof summa", ostida 3 kichik karta; aylana tez tugmalar (`.hero-btn` ichida `.hb-ic/.hb-lb`; telefonda qo'shimcha `#heroBtnHist` (admin → adminHistorySection) va `#heroBtnStud`, kompyuterda `.hb-m` yashirin); "Bo'limlar" 3 ustunli kafel (faqat nom + aylana ikonka; PRO kartalar oxirida); oq pastki menyu + markazda aylana To'lov tugmasi; bo'limlarda chapda aylana "‹" orqaga tugmasi, kulrang yumaloq maydonlar (16px — iPhone zoom qilmaydi), 50px tugmalar; o'qituvchi/xodim kabineti tepasi oq (faqat "Yorug'" mavzuda).
- Yashirilgan kartalar uchun `[style*="display: none"]` qoidasi bor (JS inline style bilan yashiradi). Kompyuter ko'rinishi o'zgarmagan.

### v9.4 (2026-11-13) — faqat index.html
- **SMS bo'limi vaqtincha yopiq (syurpriz):** `const SMS_LOCKED = true` (showSection oldida) — bosilsa "tez orada ochiladi" xabari; Sozlamalardagi "SMS Shablon sozlamalari" kartasi ham yashirin (`html.sms-locked`). **Eskiz ulangach `SMS_LOCKED = false` qilib yuklash kerak.**
- SMS kartasida qizil diagonal **"Yangi"** lentasi (`.menu-new .new-ribbon`), kompyuter yon menyusida "Yangi" belgisi (`.sb-new`).
- PRO kartalar (Yo'qlama, AI) ustidan yaltiroq nur o'tadi (`oxShine`); telefonda ular oddiy kafel o'lchamida.
- Telefon: bosh sahifadagi aylana "To'lov kiritish" olib tashlandi (pastki menyuda bor); formalar ixchamroq (44px maydon, 46px tugma); pastki menyu ikonkalari rangli; iPhone status bar (oq soat) ostida ingichka to'q chiziq.

### v9.5 (2026-11-13) — faqat index.html
- Telefon bosh sahifasi: aylana tez tugmalar olib tashlandi (`.hero-actions` yashirin); bo'limlar 3 ustunli kafel (4 ustun sinab ko'rildi — Sukhrobga yoqmadi, juda siqiq); "Kassadagi sof summa" kartasi foni shaffof, kichikroq.
- SMS kartasi oltin chegara + yaltiroq nur (`.menu-new::before`) — SMS ochilganda `menu-new` klassi va lentani olib tashlash kerak.
- Pastki menyudagi **"Sozlama"** → `openMySettings()`: faqat "Mening login va parolim" kartasi (`#settingsSection.only-me`); bosh menyudagi "Sozlamalar" — hammasi.

### v9.6 (2026-11-13) — faqat index.html
- Rahbar pastki menyusi: Asosiy • ♻️ Tiklash • [To'lov] • 🗑️ O'chirish • ⚙️ Sozlama (AI va Jadval olib tashlandi — ular kafellarda bor). Telefonda rahbar bosh sahifasidan "O'quvchini o'chirish" va "Qayta tiklash" kafellari yashirin (`body.nav-rahbar`). Admin menyusi o'zgarmagan.
- **Suzuvchi "tomchi"** (`.nb-drop`, `setupNavDrop(nav, itemSel)`): tanlangan tugma ostida shisha tomchi, prujinali animatsiya bilan suzadi; barmoq bilan surib boshqa tugmaga olib borsa bo'ladi (tezlikka qarab cho'ziladi), qo'yib yuborilganda eng yaqin tugma ochiladi. MutationObserver `active` klassini kuzatadi. O'qituvchi/xodim menyusida ham (`setTeacherTab` ichida). Faqat telefonda.

### v9.7 (2026-11-13) — backend: models, main, routers/sms + index.html — SERVERGA YUKLANGAN
- SMS matnlari Eskiz'da tasdiqlanadigan shaklga keltirildi (lotin, 1 SMS): ota-onaga `{ism} {familiya}, {oy} oyi uchun {summa} so'm to'lov qabul qilindi. Sana: {sana}. Rahmat! OLMOS XATAMOV maktabi`; rahbarga `Yangi to'lov: {ism} {familiya}, {summa} so'm, {oy} oyi. {sana} {vaqt}. OLMOS XATAMOV maktabi`; eslatma/muddati o'tgan — `DEFAULT_TEMPLATES` da. main.py migratsiyasi eski standart matnlarni yangisiga almashtiradi (qo'lda o'zgartirilganiga tegmaydi). **Matnni o'zgartirsangiz — Eskiz'da ham qayta tasdiqlatish kerak.**
- Eskiz "Mening matnlarim": 4 ta matn (ID 100988–100991) 2026-11-13 10:20 da moderatsiyaga yuborildi. Balans 303 645 so'm.
- Serverdagi `.env` ga ESKIZ_EMAIL/ESKIZ_PASSWORD/ESKIZ_FROM=4546 kiritildi; `eskiz.balance()` = 303645 — ulanish ishlayapti. Zaxira: `backend/app_zaxira_9_6`, `/root/oxmed_baza_zaxira_2026-11-13.sql`.
- Qoldi: matnlar tasdiqlangach sinov SMS → `SMS_LOCKED = false`, "Yangi" lenta/oltin nurni olib tashlash, Sozlamalarda to'lov SMS'larini yoqish.

### v9.8 (2026-11-13) — XARAJATLAR + admin uchun Umumiy jadval (backend: models, main, routers/expenses.py (yangi) + index.html)
- **Umumiy jadval adminga ham ochiq** (rahbarniki bilan bir xil); tahrirlash — `openPaymentEditor` dagi eski qoida: admin faqat o'zi kiritgan to'lovni.
- **🧾 Xarajatlar** (`#expensesSection`, rahbar + admin): jadval `expenses` (title, quantity, amount, category, note, month, timestamp, added_by, updated_by, deleted_at/by — soft delete). API `/api/expenses` GET (`?include_deleted=true` faqat rahbar) / POST / PUT `{id}` / DELETE `{id}` / POST `{id}/restore` (rahbar). Admin faqat o'zinikini o'zgartiradi/o'chiradi; kelajak sana yo'q; admin 62 kundan eski sanani kirita olmaydi. Kategoriyalar: Oziq-ovqat, Kantselyariya, Texnika, Ta'mirlash, Kommunal, Tozalik, Transport, Boshqa.
- Frontend: tez tugmalar (Non, Suv, Kartrijga rang...), forma, oy tablari, qidiruv/tur/kim filtri, kompyuterda jadval + jami, telefonda ro'yxat, ✏️/🗑️, rahbarga "O'chirilganlarni ham ko'rsatish" + ♻️ tiklash, Excel.
- **Hisob:** "Kassadagi sof summa" = tushum − (berilgan − qaytarilgan) − **xarajatlar**; pastida "xarajat: X". Umumiy jadvalda "🧾 Xarajatlar" va "✅ Xarajatdan keyin markazga" kartalari. O'qituvchi balanslari (ledger) o'zgarmaydi.
- Sinov: scratchpad `t98.py` (27 API), `pw98.py` (16 brauzer: kompyuter+telefon).

### v9.9 (2026-11-13) — faqat index.html
- Xarajatlar kartasida qizil "Yangi" lentasi (`.menu-fresh`, `data-new-until="2026-11-19"`) — 19-noyabr (Toshkent) oxirigacha turadi, keyin `renderSidebar()` boshida o'zi olib tashlanadi (kartada ham, yon menyuda ham). Boshqa kartaga shunday lenta kerak bo'lsa — `menu-fresh` + `data-new-until` + `<span class="new-ribbon">Yangi</span>`.
- **Yuklash (internet beqaror bo'lsa):** `cd ~/Desktop/python/oxmed/frontend && gzip -9c index.html | ssh root@185.196.215.247 "gunzip > /var/www/oxmed/index.new && mv /var/www/oxmed/index.new /var/www/oxmed/index.html && chmod 644 /var/www/oxmed/index.html && md5sum /var/www/oxmed/index.html"` — siqilgan va atomar (scp uzilsa fayl yarim yozilib qolgan edi, 2026-11-13).

### v10.0 (2026-11-13) — backend: routers/salary.py + index.html
- Bosh sahifada 5-karta **"Xarajatlar"** (`.kpi.k5`, qizil, `#dashExpenses`): shu oy chiqimi = berilgan oylik/avans (qaytarilgani ayirib) + markaz xarajatlari. Telefonda 4 ta kichik karta bir qatorda, summa qisqa ("−7,74 mln", `formatShortMoney`). Bosilsa Xarajatlar bo'limi ochiladi.
- `GET /api/salary/payouts-list` (rahbar+admin, faqat o'qish): har bir oylik/avans/qaytarish yozuvi (ism, fan yoki lavozim, summa, kind, timestamp). Yig'indisi `total-payouts` (ledger.net_cash_out) bilan mos — sinovda tekshirildi.
- Xarajatlar bo'limi tepasida oy tablari + hisobot: "Jami chiqim" (oylik/xarajat ulushi chizig'i bilan), "👨‍🏫 Kimga qancha berildi" (kishi bo'yicha: berildi/qaytardi/jami), "🧾 Nimalarga sarflandi" (tur bo'yicha). Kompyuterda jadval, telefonda ro'yxat. Oy — payout timestamp'idan (Toshkent).

### v10.1 (2026-11-13) — backend: routers/salary.py + index.html
- **SMS ochildi** (`SMS_LOCKED = false`): Eskiz 4 ta shablonni tasdiqladi. SMS kartasida oltin nur olib tashlandi, "Yangi" lenta 20-noyabrgacha (`menu-fresh`, `data-new-until="2026-11-20"`). Sinov SMS standart matni = tasdiqlangan ota-ona matni namunasi. SMS matni ostida ogohlantirish: o'zgartirilsa Eskiz'da qayta tasdiqlatish kerak.
- **Xarajatlar:** forma soddalashtirildi — faqat "Nima uchun", Summa, Sana, Izoh (tez tugmalar, Turi, Miqdori olib tashlandi; backend maydonlari qoldi, category='Boshqa'). Ikki rejim (`#expensesSection[data-mode]`): bosh sahifadagi qizil karta → `openExpensesReport()` — faqat hisobot ("💸 Xarajatlar hisoboti"); menyu kafeli → kiritish + ro'yxat.
- Hisobot qatorlari bosiladi: kishi → `exPersonDetail()` oynasi (har bir yozuv: sana, kim kiritgan, izoh; "📒 Hisob varag'ini ochish" → `openSalaryDetailModal`/`openStaffLedger`); xarajat → `exGoTo()` kiritish qismiga o'tib yozuvni sariq yoritadi.
- `payouts-list` endi `orphan` (o'qituvchi/xodim o'chirilgan, `teacher_id` NULL) va `date_str` qaytaradi. Hisobotda "o'chirilgan" belgisi; rahbar xato yozuvni 🗑️ (`DELETE /api/salary/payout/{id}`) bilan o'chira oladi — summa kassaga qaytadi. Sabab: "Behzod Narzullayev" 700 000 — o'qituvchi o'chirilib, "Narzullayev Behzod" qayta qo'shilgan, eski pul yozuvlari qolgan.
- **Yopilish animatsiyalari:** `.content-section.ox-leave` (orqaga: kompyuterda kichrayib so'nadi, telefonda o'ngga suriladi), `.modal.ox-closing` (fon ochiladi, oyna kichrayadi / telefonda pastga tushadi). `DOMTokenList.remove('active')` modallar uchun 260 ms kechiktiriladi (oxirgi `<script>` dagi IIFE); `showMenu` 230 ms kutadi, orada boshqa bo'lim ochilsa bekor bo'ladi (`navSeq`).
- Sinov: scratchpad `t101.py` (28 brauzer tekshiruvi, telefon + kompyuter).

### v10.2 (2026-11-13) — faqat index.html
- SMS ishga tushdi (Sukhrob sinab ko'rdi: to'lov SMS'i keladi). "Muddati o'tgan" matni bazada qo'lda o'zgartirilgan edi — `update settings set sms_template_overdue = null` buyrug'i berildi (bajarilganini tekshirish kerak). Sinov pul yozuvlari (Behzod 700 000, Umar 200 000) o'chirildi, faqat Akram Akbarov 1 000 000 qoldi.
- **Umumiy jadval — "⚙️ Ustunlar" paneli** (`BT_COL_DEFS`, `btCol(k)`, `setBtCol`, `resetBtCols`, `localStorage.oxmed_bt_cols_v1` — shu qurilmada): Sinf/Fan, Telefon, Sana, Usuli, Qarz, Kim kiritdi, Fanlar bo'yicha ulush, O'qituvchilar bo'yicha ulush, Markazga qoladi. Ism va To'lov doim bor. Standart: **"Fanlar bo'yicha" yashirin** (o'qituvchi sarlavhasida fan yozilgan). Telefon kartochkalari va **Excel ham shu tanlov bo'yicha**. Sinov: scratchpad `t102.py` (12).

### v10.3 (2026-11-13) — backend: models, main, routers/bt_columns.py (yangi) + index.html
- **Umumiy jadvalga boshliqning o'z ustunlari** ("Abet puli", "Izoh"...): jadvallar `bt_columns` (name, kind 'money'|'text', position, deleted_at) va `bt_cells` (column_id, payment_id — CASCADE, value_num/value_text; unique). API `/api/bt-columns`: GET (rahbar+admin; ustunlar+kataklar), POST/PUT `{id}`/DELETE `{id}` — faqat rahbar (ko'pi bilan 12 ta, bir xil nom yo'q), PUT `{cid}/cells/{pid}` — rahbar+admin (bo'sh = o'chirish; summa ustuniga faqat raqam).
- Frontend: "⚙️ Ustunlar" panelida "🏷️ O'z ustunlaringiz" — qo'shish (nom + 💰 Summa/✏️ Matn), ✏️ nom, 🗑️ o'chirish, ko'rinish almashtirgichi (`btCol('c'+id)`). Jadvalda binafsha "Qo'shimcha" guruhi; katak bosilsa joyida yoziladi (`btEditCellInline`, Enter/Esc); summa ustunlarining jami pastda. Telefonda kartochkada chip, bosilsa oyna (`btEditCellModal`). Excel ham. **Kassa va o'qituvchi hisobiga ta'sir qilmaydi.**
- Sinov: scratchpad `t103.py` (14 API), `pw103.py` (11 brauzer).

### v10.4 (2026-11-13) — backend: routers/teacher_self.py, routers/students.py + index.html
- **O'qituvchi o'zi o'quvchi va guruh qo'shadi** (faqat fan o'qituvchisi; xodim — 403, kabinetda ko'rinmaydi `[data-staff="1"]`): `GET/POST /api/teacher/groups`, `DELETE /api/teacher/groups/{id}` (o'quvchisi bor guruh o'chmaydi; vaqt HH:MM, boshlanish < tugash, takror yo'q), `POST /api/teacher/students` {first_name,last_name,phone(9 raqam),phone2?,group_id?} — oddiy repetitor o'quvchi (fan/o'qituvchi o'zidan, `added_by` = o'qituvchi logini; takror ism+familiya+telefon → 409). To'lov kiritilganda ulush avvalgidek avtomatik (sinovda tekshirildi).
- `POST /api/students` endi faqat rahbar/admin (`require_staff`) — avval har qanday rol qo'sha olardi.
- Kabinet: bosh sahifada "👤 O'quvchi qo'shish" va "🗓️ Guruhlarim" kartalari ("Yangi" lenta 20-noyabrgacha, `tpApplyFresh`), O'quvchilar tabida ham tugmalar; oynalar `tpOpenAddStudent`, `tpOpenGroups`.
- Jami o'quvchilar: "qo'shdi: 👨‍🏫 O'qituvchi ismi" (`whoAddedStudent` — `loginUsername` bo'yicha).
- Sozlamalardan "💡 Ma'lumot" / "⚠️ Muhim!" qutilari olib tashlandi. **"Rahbar telefon raqamlari" va "SMS Shablon sozlamalari" SMS bo'limi → ⚙️ Sozlamalar ichiga ko'chirildi** (DOM `#smsExtra` ga, `setSmsTab('settings')` da ko'rinadi, faqat rahbar).
- SMS namunalarida doim "Sukhrob Koziboyev" (`SMS_DEMO`), sinov SMS raqami 778776877. Xarajatlar placeholderlari "Kiriting".
- Sinov: scratchpad `t104.py` (18 API), `pw104.py` (12 brauzer).

### v10.5 (2026-11-13) — faqat index.html (v10.4 bilan birga yuklanadi)
- Hamma "Yangi" lentalar 2 hafta: `data-new-until="2026-11-27"` (Xarajatlar, SMS, o'qituvchi kafellari).
- Telefonda To'lov kiritish: `.pay-grid` — O'quvchi to'liq qatorda, **Oy | To'lov miqdori**, **Qarz | To'lov turi** yarim-yarim; pastda "Bekor qilish" (`cancelPaymentForm()` — formani tozalab bosh sahifaga) va "To'lovni saqlash" yonma-yon, ixcham (sticky).
- O'qituvchi bosh sahifasi — kafellar (rahbar menyusi kabi, telefonda 3 ustun, faqat ikonka + nom): 👥 O'quvchilarim, 📊 Hisob-kitob (`tpOpenCalc()` — oynada), 👤 O'quvchi qo'shish, 🗓️ Guruhlarim. Ochiq turgan "Hisob-kitob", "So'nggi yozuvlar", "O'quvchilarim" kartalari bosh sahifadan olib tashlandi. Xodimda faqat "Hisob-kitob" kafeli (`.tp-only-teacher`). Yangi bo'lim qo'shilsa — `.tp-actions` ichiga yana bitta `.tp-act` tugma.
- Sinov: scratchpad `pw105.py` (11).

### v10.6 (2026-11-13) — backend: routers/sms.py, routers/teacher_self.py, schemas.py + index.html
- **Xato:** deploy/restart'dan keyingi birinchi SMS'lar "Eskiz javobi: Token used before issued" bilan ketmadi (yangi tokenning iat'i Eskiz tekshiruvchisidan oldinda — soat farqi). **Tuzatish:** `_login()` dan keyin `_wait_until_valid()` token iat/nbf kelguncha kutadi (≤10 s); `_request()` javobda "before issued"/"not yet valid" bo'lsa 2/4/6 s kutib qayta urinadi (4 urinish). Sinov: soxta javob bilan — 3-urinishda yuborildi.
- **O'qituvchi kabinetida "to'lanmagan" xatosi:** to'lov boshqa oy (Dekabr) uchun kiritilgan edi, kabinet faqat joriy oyni ko'rsatardi; bundan tashqari to'lovlar ism matni bo'yicha bog'lanardi (bir xil ismlilar aralashardi). Endi `/api/teacher/dashboard` to'lovlarni **student_id** bo'yicha (id'siz eski yozuvlar — ism bo'yicha) oladi va `paid_months` {oy: summa}, `month_paid`, `added_by` qaytaradi; ro'yxatda "✅ Noyabr to'langan / ⏳ Noyabr to'lanmagan" + har bir to'langan oy chipi (`tpPaidMonthsHtml`). Sinov: scratchpad `t106.py` (5).

### v10.7 (2026-11-13) — faqat index.html (v10.6 bilan birga yuklanadi)
- O'qituvchi "O'quvchilarim": tepada **oy tanlash** qatori (`#tpMonths`: 📅 Barcha oylar + to'lov bo'lgan oylar + joriy oy, "＋ Oy" bilan boshqasi; `tpSetMonth`), **Jami / To'lagan / To'lamagan kartalari bosiladi** — ro'yxat shu bo'yicha filtrlanadi (`teacherStudentFilter`), pastida "X bo'yicha to'langan: … so'm". Holat tanlangan oy bo'yicha (`tpStuPaid`); "Barcha oylar" — biror marta to'laganlar. Pastdagi yashil oy chiplari olib tashlandi; eski `.tp-filter` yashirin.
- Yangi kabinet elementlari (kafellar, tugmalar, oy chiplari, qidiruv, badge'lar) **Tungi va Shaffof mavzularda** ham moslashtirildi. Sinov: scratchpad `t107.py` (7) + 3 mavzu skrinshoti.

### v10.8 (2026-11-13) — backend: routers/teacher_self.py, schemas.py + index.html
- O'qituvchi kabineti: tepadagi **O'quvchilar / To'lov qilgan / To'lov qilmagan bosiladi** → ro'yxat shu filtr bilan (`tpOpenList`). Ro'yxatda to'lov vaqti (🕐 sana soat); o'quvchi bosilsa — barcha to'lovlari: qaysi oy, 📅 sana, 🕐 soat, summa + qo'ng'iroq (`tpStudentPayments`). Backend `/api/teacher/dashboard` har o'quvchiga `payments: [{month, amount, date_str}]`.
- Tungi/Shaffof mavzuda tepadagi uchta raqam ham alohida kartochka (yorug'dagidek), sarlavha bir xil.
- Kabinet pastida versiya: "OXMED Pro 10.8 • oxmed.uz" (`.tp-version`, har tabda).
- Kompyuter: "Markaz rahbari" yonida **⟳ Yangilash** (`manualRefresh()`, telefonda yashirin — u yerda pastga tortish). Yon menyudan PRO bo'limlar (Yo'qlama, AI) olib tashlandi (bosh sahifada qoladi).
- Sinov: scratchpad `t108.py` (10).

### v10.9 (2026-11-13) — SERVERGA YUKLANGAN — BITTA O'QUVCHI — BIR MARTA; ko'p o'qituvchili o'quvchi (backend: models, student_links.py (yangi), routers/students.py, routers/teacher_self.py, schemas.py + index.html)
- Yangi jadval `student_teachers` (student_id, teacher_id CASCADE, group_label, added_by, added_at; unique). O'quvchi bazada bir marta; boshqa o'qituvchilar uni shu jadval orqali "O'quvchilarim"ga biriktiradi.
- `student_links.py`: `find_duplicates()` (ism+familiya, joyi almashgani ham; apostrof/katta-kichik farqsiz; `same_phone` belgisi; kim qo'shgani `who_label` — Admin/Rahbar/"Vali (Matematika o'qituvchisi)"; qaysi o'qituvchilarda o'qishi).
- `POST /api/students` (rahbar/admin): bir xil ismli bo'lsa **409 `duplicate_student`** → oynada "avval X tomonidan qo'shilgan" + "Ha, baribir qo'shaman" (`allow_duplicate`). `GET /api/students` endi **faqat rahbar/admin** (avval o'qituvchi ham hammani ko'rardi) va har o'quvchiga `teachers` [{id,name,subject}] (asosiy + biriktirilgan + to'lovdan ulush olgan) — Jami o'quvchilarda "Matematika - Vali, Kimyo - Ali".
- `POST /api/teacher/students`: takror bo'lsa 409 → oynada "➕ Ha, shu o'quvchi — o'quvchilarimga qo'shish" (`link_student_id`, yangi o'quvchi YARATILMAYDI) yoki "Yo'q, bu boshqa bola" (`force_new`). `DELETE /api/teacher/students/{id}/link` — faqat biriktirilganini o'z ro'yxatidan chiqaradi (bazada qoladi).
- **O'qituvchi ro'yxati** (`my_students`): asosiy (own) + biriktirilgan (link, "🔗 biriktirilgan") + **to'lovdan unga ulush ajratilgan** (pay, "💵 to'lov orqali" — rahbar to'lovni qaysi o'qituvchiga bo'lsa, o'quvchi o'sha o'qituvchida avtomatik chiqadi). **To'lov holati faqat shu o'qituvchiga tegishli to'lovlar** (`teacher_payments`: ulush ajratilgan; asosiy o'quvchida umuman bo'linmagan to'lov ham) — boshqa fanga to'lagan bo'lsa bu o'qituvchida "to'lamagan". Tafsilotda "sizga: ulush".
- Hisob-kitob (ledger, kassa) o'zgarmaydi. Sinov: scratchpad `t109.py` (22 API), `pw109.py` (7 brauzer).

### v11.0 (2026-11-13) — faqat index.html — SERVERGA YUKLANGAN
- O'qituvchi kabinetida **📋 Yo'qlama** kafeli (`.tp-act.tp-locked`, rahbar menyusidagi PRO uslubida: to'q fon, oltin chegara, qulf, "🔒 Yopiq • 200 $", yaltiroq nur) → `showLockedFeature('attendance')`. Xodimda ko'rinmaydi (`.tp-only-teacher`). Barcha mavzularda bir xil.

### v11.1 (2026-11-13) — backend: routers/students.py + index.html
- `GET /api/students` → `teachers` har biriga `group` (o'sha o'qituvchidagi guruh: asosiy — students.group_label, biriktirilgan — student_teachers.group_label) va `source` (own/link/pay).
- Admin/rahbar To'lov kiritish: o'qituvchi tanlansa, o'qituvchi **biriktirgan va to'lovdan ulush olgan** o'quvchilar ham chiqadi (`studentHasTeacher`), guruh filtri o'qituvchiga xos guruh bo'yicha (`studentGroupFor`); ro'yxatda "Familiya Ism — Fan • O'qituvchi • kunlar • soat"; avtomatik ulush **tanlangan o'qituvchiga** (o'quvchi unda o'qisa). O'qituvchi kabinetida qo'shgan guruhlar admin guruh ro'yxatida avvaldan chiqadi (bitta `groups` jadvali). Sinov: scratchpad `t111.py`/`t111b.py` (5).

### v11.2 (2026-11-13) — faqat index.html (v11.1 backend bilan birga yuklanadi)
- **O'quvchi kartasi** (`openStudentCard(id)`): Jami o'quvchilarda qatorga bosilsa (kompyuter `.st-tap`, telefon `studentRowActions` endi kartani ochadi) — telefon(lar), **bazaga kim qo'shgan + sana va soat**, jami to'lagan, **qaysi o'qituvchilarda o'qiydi** (fan, guruh kunlari/soati, asosiy / o'qituvchi o'zi qo'shgan / to'lov orqali), **to'lovlar tarixi** (oy, sana, soat, usul, kim kiritgan, kimga qancha ulush), qarz; tugmalar: Qo'ng'iroq, Tahrirlash, Qarz, Yopish. Sinov: scratchpad `t112.py` (6).

### v11.3 (2026-11-13) — faqat index.html
- **Xato tuzatildi:** o'qituvchi "Guruhlarim"da kun tugmalari (Toq/Juft/Har kuni) bosilmasdi — `tpPickGroup` faqat `.tp-gchip` ni almashtirardi, kun tugmalari `.tp-day`. Endi bosilgan tugma turiga qarab ishlaydi.
- O'qituvchi Profilida "🔐 Login va parol" endi **yig'ilgan qator** (`<details id="tpCredBox" class="tp-cred">`, "O'zgartirish uchun bosing ›"); bosilsa ochiladi, saqlangach yana yopiladi. Sinov: scratchpad `t113.py` (16, kompyuter + telefon, 3 mavzu).

### v11.4 (2026-11-13) — faqat index.html
- **Xato:** o'qituvchi kabinetida qo'shgan guruh rahbarning Sozlamalar → "O'qituvchilar va guruhlar boshqaruvi"da ko'rinmasdi — Sozlamalar xotiradagi (ilova ochilgandagi/keshdagi) eski ma'lumotdan chizilardi. Endi Sozlamalar ochilganda `refreshAppData({silent:true})` serverdan yangisini oladi va `refreshActiveViews()` Sozlamalar ochiq bo'lsa `loadTeachersList()`/`loadSubjectsList()` ni qayta chizadi (⟳ va pastga tortish ham). Bazada guruh bitta `groups` jadvalida — backend o'zgarmadi. Sinov: scratchpad `t114.py` (4).

### v11.5 (2026-11-13) — faqat index.html (v11.4 bilan birga yuklanadi)
- Kirish sahifasida "Parolni unutdingizmi?" tepasida **"📲 Ilovani o'rnatish"** kartasi (`#installLinkBtn`, `.login-box .install-link` — ikonka + "Ekranga OXMED belgisi qo'shiladi" + ›) **doim ko'rinadi** (avval ilova ichida ochilganda yashirinardi). Bosilsa `installApp()`: Android/Chrome — darhol o'rnatish oynasi, iPhone — qadamlar oynasi, kompyuter — ko'rsatma. Ilova sifatida ochilgan bo'lsa — yashil "✅ Ilova o'rnatilgan", bosilsa xabar. Sinov: scratchpad `shot_login.py`, `t115.py`.

### v11.6 (2026-11-13) — index.html + manifest.json
- **Xato:** Android'da Google ilovasi ichida oxmed.uz ochilganda kirish sahifasida "✅ Ilova o'rnatilgan" chiqardi (ichki brauzer `display-mode: standalone` deb javob beradi). Endi `isInstalledLaunch()`: iPhone `navigator.standalone`, Android'da esa `manifest.json` `start_url: "/?src=pwa"` (sessionStorage `oxmed_pwa`) yoki `android-app://` referrer + display-mode + ichki brauzer EMAS. O'rnatish UI faqat shunga qaraydi (`isStandaloneApp` boshqa joylar uchun qoldi). `manifest.id` "/" o'zgarmadi — o'rnatilgan ilovalar ikkilanmaydi.
- Google ilovasi (`GSA/`), Yandex, OK ham ichki brauzer deb aniqlanadi; o'rnatish oynasida **"🌐 Chrome'da ochish"** (Android, `intent://...package=com.android.chrome`) yoki **"🧭 Safari'da ochish"** (iPhone, `x-safari-https://`) tugmasi.
- Google qidiruvida "Yuklab olish" tugmasi faqat Play Market/App Store'dagi ilova uchun chiqadi — sayt buni qila olmaydi. Play Market uchun TWA (Bubblewrap/PWABuilder, Google Play akkaunt 25 $ bir marta) — keyinroq. Sinov: scratchpad `t116.py` (10).
- Yuklash: `cd ~/Desktop/python/oxmed/frontend && tar czf - index.html manifest.json | ssh root@185.196.215.247 "cd /var/www/oxmed && tar xzf - && chmod 644 index.html manifest.json && md5sum index.html manifest.json"`

### v11.7 (2026-11-14) — backend: ledger.py, routers/teacher_self.py, routers/payments.py, routers/students.py + index.html
- **O'qituvchi o'quvchining to'liq to'lov summasini ko'rmaydi — faqat rahbar unga ajratgan ulushni.** `/api/teacher/dashboard`: `paid_months` {oy: ULUSH}, `month_paid`, `total_paid` — ulushlar yig'indisi; `payments` [{month, share, date_str}] (`amount` yo'q). Oy kaliti bor = to'langan (ulush 0 bo'lsa ham — bo'linmagan to'lov). `/api/teacher/ledger` → `teacher_ledger(..., hide_payment_amount=True)` — izohda "to'lov X so'm" yo'q (rahbar/xodim varag'ida bor).
- Kabinet: `tpIsPaid()` (holat), `tpStuPaid()` (ulush); "sizga: X so'm", "ulush hali ajratilmagan", "Noyabr bo'yicha sizga ajratilgan", oynada "sizga ajratildi".
- **Xavfsizlik teshigi yopildi:** `GET/POST /api/payments`, `PUT /api/payments/{id}`, `DELETE /api/students/{id}`, `POST /api/students/bulk` avval har qanday login (o'qituvchi ham) bilan ochilardi → endi `require_staff` (rahbar/admin). Kabinet ularni ishlatmaydi.
- Sinov: scratchpad `t117.py` (17), t109 (22), t98 (27), t106 (yangilangan, 5). Mac zaxirasi: `_backup_2026-11-14_v11.6/`.

### v11.8 (2026-11-14) — backend: student_links.py, schemas.py, routers/students.py, routers/teacher_self.py + index.html
- **Aqlli o'xshashlik** (`student_links.canon/compare_names/find_duplicates`): kirill→lotin, apostroflar, x/h/kh, q/k, ye/e, iy/i, dj/j, ikki harf tenglashtiriladi + Levenshtein (1 harf ≥4 belgi, 2 harf ≥8), ism-familiya joyi almashgani. `match`: exact | similar | sibling (telefon+familiya bir xil, ism boshqa — aka-uka, faqat ogohlantirish). `exact_same` (ism + telefon bir xil) → **hech qachon qo'shilmaydi** (admin `allow_duplicate`, o'qituvchi `force_new` ham o'tmaydi; o'qituvchiga faqat "biriktirish").
- **Tahrirlash** (`PUT /api/students/{id}`, yangi `allow_duplicate`): boshqa o'quvchi bilan bir xil qilib qo'yilsa 409 — oynada "🔗 Birlashtirish" (aniq bir xil bo'lsa saqlab bo'lmaydi).
- **Birlashtirish** `POST /api/students/{id}/merge {into_id}` (rahbar/admin): to'lovlar (student_id/ism/telefon), qarzlar (bir oyda ikkalasi bo'lsa — kattasi), student_teachers, asosiy o'qituvchi (link sifatida), phone2, sms_logs o'tadi; ortiqchasi o'chadi. Ulushlar/summalar o'zgarmaydi (testda kassa va balans tekshirilgan). `GET /api/students/duplicates` — bazadagi takroriy juftliklar (exact, yoki similar+bir xil telefon).
- **Jami o'quvchilar:** 4 ta kichik ko'rsatkich (Jami/Maktab/Repetitor/Qarzdor — bosiladi), "⚠️ takroriy yozuv" banneri (birlashtirish tugmasi bilan), kompyuterda ixcham jadval (№, O'quvchi, Telefon, O'qishi chiplari, Qo'shgan+sana, To'lagan, Qarz, ✏️🔴; ustun bo'yicha tartiblash, sarlavha yopishqoq), telefonda ixcham qatorlar (`renderStudentsTableV2`).
- **Menyu papkalari:** bosh sahifada To'lov kiritish qoladi; 📂 O'quvchilar (qo'shish, jami, o'chirish), 📂 Xodimlar (O'qituvchilar hisob-kitobi, Fanlar bo'yicha foizlar — `openSalaryView('teachers'|'subjects')`, Markaz xodimlari), 📂 Sozlamalar (kafellar: login/parol, admin logini, maxfiy parol, fanlar, o'qituvchilar va guruhlar + Qayta tiklash + Hisobotlar; kafel → faqat o'sha panel `settingsShowPanel`). Ichki kartalar `.in-folder[data-folder]` (rol ko'rinishi avvalgidek), `FOLDERS`, `openFolder`, `#folderSection`. "Orqaga" (`goBack`) — papkadan ochilgan bo'lsa papkaga. Admin ham Sozlamalarni ko'radi (login + qayta tiklash).
- **Yon menyu (kompyuter):** papkalar guruh — "›" strelka, bosilsa pastga buriladi, ichidagilar ochiladi va papka sahifasi ochiladi (`sbToggleGroup`, `sbKid`).
- Bosh sahifadagi "Ilovani o'rnating" banneri: ✕ faqat shu safar (sessionStorage) — o'rnatilmaguncha har safar chiqadi; o'rnatilgan ilovada chiqmaydi.
- Sinov: scratchpad `t118.py` (23 API), `pw118.py` (60 brauzer: rahbar/admin × kompyuter/telefon), t117/t109/t106/t113/t114 qayta o'tdi.

### v11.9 (2026-11-14) — backend: routers/recycle.py + index.html
- **Xato (500):** "Qayta tiklash"da to'lov tiklanmasdi — to'lov o'quvchi bilan birga o'chirilgan bo'lsa, eski `student_id` bazada yo'q (FK xatosi). Endi `_resolve_student_id`: o'quvchi bo'lmasa ism (canon) + telefon bo'yicha qidiriladi, topilmasa o'quvchisiz tiklanadi. **O'quvchi tiklansa** — u bilan birga o'chirilgan to'lovlari ham avtomatik qaytadi (yangi id ga, ulushlari bilan) va avval o'quvchisiz tiklangan to'lovlari unga qayta bog'lanadi. Sinov: scratchpad `t119.py` (16 — balans har qadamda tekshirilgan).
- Jami o'quvchilar jadvalida o'qituvchilar ko'rsatilmaydi — ustun "Sinf / fan": sinf + "📚 Fan" yoki "📚 N ta fan" (batafsili o'quvchi kartasida).

### v11.10 (2026-11-14) — faqat index.html
- Papka kartalaridagi "3 ta bo'lim" / "7" raqamlari olib tashlandi (kompyuter va telefon).
- **Pastki menyu tomchisi iPhone'da barmoq bilan surilmasdi** (Asosiy ustida qolib ketardi): `.mobile-bottom-nav, .tp-nav` da `touch-action` yo'q edi — Safari gorizontal surishni o'zi olib, `pointercancel` yuborardi. Endi `touch-action: none` (+ user-select/touch-callout o'chiq). Bosish avvalgidek. WebKit'da bosish va surish sinaldi; haqiqiy iPhone'da tekshirish kerak.

### v11.11 (2026-11-14) — faqat index.html
- O'qituvchi kabinetida **📚 Uy vazifalari** — qulflangan PRO kafel (Yo'qlama uslubida, to'q binafsha fon `.tp-lock-hw`, oltin chegara, nur), `showLockedFeature('homework')` → "180 $" oynasi (vazifa berish, o'quvchi yuklaydi, tekshirish/baho, kim topshirdi). Xodimda ko'rinmaydi. O'quvchilar kabineti bilan birga ishga tushiriladi. Sinov: scratchpad `t120.py` (10, 3 mavzu × telefon/kompyuter).
- **Rejada — O'QUVCHI KABINETI** (2026-11-14 taklif qilingan, Sukhrob javobi kutilmoqda): 4 tab (Asosiy, Darslarim, To'lovlarim, Profil); login admin "Kirish berish" bilan, ota-onaga SMS (yangi Eskiz shabloni kerak); "Farzandlarim" (bitta telefon — bir nechta farzand); jadval guruhlardan avtomatik; o'quvchi faqat o'z ma'lumotini ko'radi. Ochiq savollar: login telefonmi yoki ID; ota-ona va o'quvchi bitta loginmi.

### v11.12 (2026-11-14) — faqat index.html: KIRISH SAHIFASI — PRO DIZAYN
- Bayroq foni qoldi (+ yengil yorug'lik o'tishi). HTML: `.login-shell` > `.login-side` (faqat kompyuterda) + `.login-box`. ID'lar o'zgarmadi (`loginForm`, `username`, `password`, `bioLoginBtn`, `installLinkBtn`).
- **Kompyuter (≥900px):** ikki qismli panel — chapda to'q ko'k brend qismi (logo, "To'lovlar, o'quvchilar va hisob-kitob — bitta joyda", 4 ta imkoniyat, "Tizim ishlayapti • kun, soat" — `lsClock`), chap chetida bayroq chizig'i; o'ngda "Xayrli tong/kun/kech/tun" (`lbGreet`, Toshkent vaqti, `loginTick`) + "Tizimga kirish". Past ekranlarda (≤820px balandlik) ixcham.
- **Telefon:** pastdan chiqadigan oq kartochka (yuqori burchaklar 32px), logo kartaning tepasida suzib turadi.
- Maydonlar ichida ikonka, parolni ko'rsatish 👁 (`toggleLoginPw`), "Kirish →" tugmasi gradient + nur + yuklanish aylanasi (`.login-go.loading`; submit handler `.lg-t` matnini almashtiradi), xato parolda kartochka silkinadi (`.shake`), Touch ID tugmasida barmoq izi SVG, ilova o'rnatilgan bo'lsa kichik yashil belgi, "🔒 Himoyalangan ulanish". `prefers-reduced-motion` da animatsiyasiz. Sinov: scratchpad `t121.py` (36: 1440/1280 kompyuter, iPhone/SE, WebKit standalone).

### v11.13 (2026-11-14) — faqat index.html — SERVERGA YUKLANGAN (11.11 bilan birga)
- **Zoom o'chirildi:** viewport `maximum-scale=1, user-scalable=no`; `html, body { touch-action: manipulation }` (2 marta bosish); iOS Safari uchun `gesturestart/change/end` va ko'p barmoqli `touchmove` `preventDefault`.
- **Tortib yangilash (faqat o'rnatilgan ilova):** shisha "pill" — tortgan sari to'ladigan doira (SVG `stroke-dashoffset`), "Qo'yib yuboring", aylanish "Yangilanmoqda…", keyin ✓ "Yangilandi" / ! "Internet yo'q". Tezroq: rezina koeffitsiyenti 0.75 (80px gacha), TRIGGER 56 (≈75px barmoq; avval ≈140px), sun'iy 450ms kutish olib tashlandi.
- **Kirish sahifasi (v11.12 dizayni almashtirildi):** bitta tiniq shisha kartochka (`backdrop-filter: blur(28px) saturate(190%)`, oq gradient chegara), orqada suzuvchi rangli dog'lar (`.lg-blob`), logo, "Xayrli tun", "OLMOS XATAMOV", Login/Parol (ikonka + 👁), pastda "Parolni unutdingizmi?" va kichik "Ilovani o'rnatish" chip. Yon panel, ortiqcha matnlar olib tashlandi. Versiya matni `<p>` yashirin.
- **"Kirish" tugmasida odamcha** (`#loginGo`, SVG `.kid` + `.school`): `--p` = login (4 belgigacha) 50% + parol (6 belgigacha) 50% — yozgan sari maktab tomon yuradi (`.walking` oyoq/qo'l animatsiyasi), bo'sh bo'lsa qo'l silkitadi (`.idle`), to'liq bo'lsa sakraydi (`.ready`, "Kirish →"). Bosilganda (`.go`) eshik oldiga yuradi (so'rov bilan parallel, ≥650ms); to'g'ri → `.enter` (eshik ochiladi, derazalar yonadi, odamcha kichrayib kirib ketadi, 780ms) → `completeLogin`; xato → `.bonk` (urilish, yulduzchalar, qo'l boshda) → `.angry` (yuzi ekranga, qoshlar chimirilgan, 💢, oyoq tepadi, "Xato! Qayta urining", kartochka silkinadi) → 1.5s dan keyin joyiga qaytadi (`resetLoginKid`, logout'da ham). `prefers-reduced-motion` da animatsiyasiz.
- Kirish sahifasida logo oq fonsiz — faqat logoning o'zi (shaffof PNG) + `drop-shadow`.
- **Diqqat (tuzatilgan xato):** v11.13 qayta yozishda formaga eski login maydoni nusxasi tushib, `required` bo'sh maydon formani to'xtatgan edi — tuzatildi; endi `#username`/`#password` bittadan. Sinov: scratchpad `t122.py` (45: kompyuter, telefon, WebKit iPhone; zoom; tortib yangilash), `kidshots.py` (kadrlar).

### v11.14 (2026-11-14) — index.html, manifest.json, sw.js + yangi belgilar: "OLMOS NURI" — SERVERGA YUKLANGAN
- Bayroq o'rniga **"Olmos nuri"** uslubi: to'q ko'k fon (#070d24 → #0f1a4a → #1d1650), havorang/binafsha yorug'liklar, olmos qirralari (SVG), sekin aylanadigan nurlar (`#loginPage::before`), logo ortida porlash (`::after`).
- Kirish kartochkasi — **tiniq shisha (suv tomchisi)**: `blur(16px) saturate(170%)`, juda shaffof oq gradient, ichki yorug'lik/soya (bo'rtib turadi), burchaklarda oq yaltiroq chegara (`::after` mask), chap tepada yaltiroq dog'. Matnlar oq, maydonlar shaffof, autofill ham to'q.
- **Yangi belgilar** (fon bilan bir xil uslub, logo markazda porlab turadi): `icon-ox-192.png`, `icon-ox-512.png`, `icon-ox-maskable-512.png`, `apple-touch-icon-ox.png` (180), `favicon-ox.png` (64). Yasash: scratchpad `mkicon_gem.py` (Playwright bilan HTML/CSS → PNG; PIL kerak emas). manifest/sw.js/index.html havolalari yangilandi, `background_color` #0b1533. Eski `-uz` belgilar qoldi (o'chirilmagan). iPhone'da belgi faqat ilovani o'chirib qayta qo'shganda yangilanadi.
- Yuklash: `cd ~/Desktop/python/oxmed/frontend && tar czf - index.html manifest.json sw.js icon-ox-192.png icon-ox-512.png icon-ox-maskable-512.png apple-touch-icon-ox.png favicon-ox.png | ssh root@185.196.215.247 "cd /var/www/oxmed && tar xzf - && chmod 644 index.html manifest.json sw.js *-ox*.png && md5sum index.html"`

### v11.15 (2026-11-14) — faqat index.html (v11.14 fayllari bilan birga yuklanadi) — SERVERGA YUKLANGAN
- **Odamcha olib tashlandi → "OLMOS QULF"** (`#loginGo`): tugma login+parol to'lmaguncha `disabled` (shisha, "Loginni kiriting" → "Parolni kiriting"); yozgan sari chapdan zaryadlanadi (`.lg-fill` kengligi `--p`, uchida yorug' chiziq) va olmosning 9 ta qirrasi (`.gem .f`, `--o` tartibi) bittadan yonadi; to'liq → `.ready` (ko'k-binafsha, nur o'tadi, olmos porlaydi, "Kirish →"). Bosilsa `.busy` (qirralar bo'ylab nur, olmos aylanadi, "Tekshirilmoqda…", ≥550ms); to'g'ri → `.ok` (olmos 10 ta zarrachaga sochiladi, havorang, "Xush kelibsiz", ekran chaqnaydi `#lgFlash`) → `completeLogin`; xato → `.bad` (olmos yoriladi `.gem-crack`, qizil, titraydi, "Login yoki parol xato", 1.5s dan keyin bitadi). Chrome avto-to'ldirishi `animationstart` (`oxAutofill`) orqali seziladi.
- **Safari xatosi (tuzatildi):** tugma matnini har `change`da qayta yozish WebKit'da "click"ni bekor qilardi (xato parol → to'g'ri parol kiritilganda kirmasdi) — endi matn faqat o'zgarganda yoziladi.
- **"Parolni saqlash"** (`#savePw`): to'g'ri kirilganda login + parol `localStorage['oxmed_saved_login_v1']` ga **AES-GCM bilan shifrlangan** holda (kalit IndexedDB `oxmed_secure`, non-extractable `CryptoKey`); Chrome'da `PasswordCredential` ham. Sahifa ochilganda / logout'dan keyin `fillSavedLogin()` to'ldiradi. Belgi olinsa — darhol o'chiriladi; 401 bo'lsa saqlangani o'chadi. Sinov: scratchpad `t123.py` (45: kompyuter, telefon, WebKit), `gemshots.py`.

### v11.16 (2026-11-14) — backend: models, main, schemas, utils, ledger, routers/teachers, routers/staff, routers/salary, routers/sms + index.html — SERVERGA YUKLANGAN
- **Xodim va o'qituvchi telefoni:** `teachers.phone` (9 raqam, `utils.clean_staff_phone`); o'qituvchi qo'shishda (`TeacherIn.phone`), xodim formasida (`StaffIn.phone`, tahrirda berilmasa o'zgarmaydi), `PUT /api/teachers/{id}/phone` (rahbar; xodimlar uchun ham). `/teachers`, `/staff`, `/salary/overview` da `phone`. Frontend: `.ph-chip` ("📞 +998 …" / "📵 Telefon qo'shish") — Sozlamalar o'qituvchilar ro'yxati, Oylik kartochkalari, Xodimlar; `openPhoneEditor`.
- **Avans / Oylik:** `teacher_payouts.ptype` ('avans'|'oylik') va `month` (qaysi oy uchun; bo'sh — joriy oy). Faqat `kind='payout'` da. Hisob varag'i: "Noyabr oyi uchun avans berildi" / "... oylik berildi". `payouts-list` da ham. Kartochkalarda **ikki tugma**: "💵 Avans berish" (yashil) va "🏦 Oylik berish" (binafsha); oynada tur almashtirgich (`payTypeBlock`, `ptPick`, `ptVal`), oy tanlash, **SMS jonli namunasi** + telefon holati (yo'q bo'lsa shu yerda qo'shish `ptSavePhone`). Xodimlarda "↩️ Qaytardi" alohida tugma (qarzi bo'lsa).
- **SMS:** `routers/sms.py` `PAYOUT_TEMPLATES` — `{fio}, siz {oy} oyi uchun {summa} so'm avans|oylik oldingiz. {sana} {vaqt}. OLMOS XATAMOV maktabi`; `send_payout_sms` (BackgroundTasks, kind `staff` jurnalda). `settings.sms_to_staff` (standart TRUE) — SMS sozlamalarida "Xodimlarga avans / oylik SMS'i" kaliti + ikkala matn ko'rsatiladi. Javobda `sms`: queued | no_phone | off. **Ikkala matn Eskiz "Mening matnlarim"da tasdiqlanishi kerak** (aks holda jurnalda xato).
- Sinov: scratchpad `t124.py` (21 API + soxta Eskiz bilan SMS), `pw124.py` (26 brauzer). Mac zaxirasi: `_backup_2026-11-14_v11.15/`.

### v11.17 (2026-11-14) — backend: schemas.py, routers/teacher_self.py + index.html
- **O'qituvchi/xodim o'z telefonini kiritadi:** `PUT /api/teacher/phone` (require_teacher; `clean_staff_phone`), `/api/teacher/dashboard` → `phone`. Bitta `teachers.phone` ustuni — o'qituvchi kiritsa rahbarda (Sozlamalar, Oylik, Xodimlar) ko'rinadi, rahbar kiritsa kabinetda; avans/oylik SMS'i shu raqamga. Profilda birinchi karta "📞 Telefon raqamim" (`tpRenderPhone`, `tpSavePhone`; "✅ Saqlangan" / "⚠️ Hali kiritilmagan — SMS kelmaydi"), 3 mavzuda.
- **📖 Darsliklar** kafeli (bosh sahifada Uy vazifalari o'rnida, "Yangi" lenta 28-noyabrgacha; xodimda yo'q) → `tpOpenLessons()`: 📚 Uy vazifalari (🔒 180 $), 📝 Test natijalarini kiritish (🔜 Tez orada), 📈 O'zlashtirish (🔜 Tez orada) → `showLockedFeature('homework'|'tests'|'progress')`; `LOCKED_FEATURES` da `soon: true` — narx o'rniga "🔜 Tez orada". Narx belgilansa: `soon` ni olib, `price` qo'shish.
- **O'quvchilarim:** har bir o'quvchida bosiladigan telefon (`.ss-phone`, `tel:`).
- Eskiz: avans (ID 101229) va oylik (ID 101230) matnlari 2026-11-14 12:43 da moderatsiyaga yuborildi (haqiqiy namuna bilan + izoh). Sinov: scratchpad `pw125.py` (22).

### v11.18 (2026-11-14) — faqat index.html (v11.17 backend bilan birga yuklanadi)
- **O'qituvchi Profili — kafellar** (rahbar menyusidek, `.tp-prof-tiles`): 📞 Telefon raqamim (telefon yo'q bo'lsa to'q sariq pulslanuvchi nuqta `.need`), 🎨 Ko'rinish rejimi, 🔐 Login va parol, 📲 Ilovani o'rnatish (`installApp()`; o'rnatilgan bo'lsa "✅ Ilova o'rnatilgan"). Kafel → `tpProfOpen(k)` faqat o'sha panel (`.tp-pp[data-pp]`, sarlavha o'zgaradi), "‹ Profil" → `tpProfBack()`. Profil tabiga qayta kirganda kafellar. **"Tez kirish" (barmoq izi) profildan olib tashlandi** (kirish sahifasidagi tugma qoldi). Eski `tpCredBox` (details) yo'q.
- **Darsliklar — alohida sahifa** (`.tp-tab[data-tab="lessons"]`, `setTeacherTab('lessons')`, pastki menyuda "Asosiy" belgilanadi, "‹ Bosh sahifa"): 3 ta kvadrat PRO kafel — 📚 Uy vazifalari (🔒 180 $), 📝 Test natijalari (🔜 Tez orada, firuza `.tp-lock-ts`), 📈 O'zlashtirish (🔜 Tez orada, yashil `.tp-lock-pg`). Pastdan chiqadigan oyna ishlatilmaydi. Sinov: scratchpad `pw126.py` (30).

### v11.19 (2026-11-14) — backend: routers/salary.py + index.html
- **Xato:** "O'qituvchilar hisob-kitobi"da O'quvchilar / To'lagan (shu oy) / To'lamagan faqat asosiy (students.teacher_name) o'quvchilarni ism bo'yicha sanardi — kabinetdagidan farq qilardi (Vali: 1 vs 12). Endi `/api/salary/overview` `teacher_self.my_students` + `teacher_payments` bilan (asosiy + biriktirilgan + to'lovdan ulush olgan; to'lagan = shu oy uchun shu o'qituvchiga tegishli to'lovi bor) — kabinet bilan aynan mos (sinovda tekshirildi).
- **Xodim kartochkasi qayta loyihalandi** (`.sx-card`, `#staffList` grid minmax 400px / telefonda 1 ustun): aylana avatar + ism + lavozim, o'ngda balans; 3 ta teng ko'rsatkich (Oylik, Boshlangan, Login); telefon qatori (`.sx-phone`, yo'q bo'lsa sariq "Telefon qo'shish — SMS uchun"); 2 ta katta tugma "💵 Avans berish" / "🏦 Oylik berish" (+ qarz bo'lsa "↩️ Pul qaytardi"); pastda bir qatorda ikonka-tugmalar: Bonus, Hisob, Tahrir, Login, Kod, O'chirish. Tungi rejim ham.

### v12.0 (2026-11-14) — YO'QLAMA OCHILDI (backend: models.py, main.py, routers/attendance.py (yangi) + index.html)
- Jadvallar `attendance_sessions` (group_id+date unique, teacher_id, group_label, created/updated by/at) va `attendance_marks` (session_id+student_id unique, status 'present'|'absent', reason ≤200). `create_all` yaratadi. **Hisob-kitobga aloqasi yo'q** (sinovda balans/kassa tekshirilgan).
- API `/api/attendance`: `GET /groups?date` (o'qituvchi — o'z guruhlari, admin/rahbar — hammasi; `scheduled` toq=Du/Chor/Ju, juft=Se/Pay/Sha, harkuni=Du–Sha), `GET /session?group_id&date`, `POST /session` (hamma o'quvchi belgilanishi shart; o'qituvchi faqat BUGUN, admin/rahbar istalgan o'tgan kun; kelajak — yo'q), `GET /report?group_id&month=YYYY-MM`, `GET /risk` (ketma-ket 3+ kelmagan), `GET /student/{id}` (rahbar/admin). Guruh o'quvchilari = `my_students` dagi shu guruh yorlig'idagilar.
- Frontend modul `ATT`/`attOpen(rootId)`: rahbar/admin `#attendanceSection` (`#attRoot`), o'qituvchi tab `data-tab="attendance"` (`#tpAttRoot`, `tpOpenAttendance`). Kun tanlash (‹ ›, kalendar), o'qituvchi filtri, "Bugungi darslar" + "Boshqa guruhlar", xavfli ro'yxat; har o'quvchida ✓ (yashil) / ✗ (qizil + sabab: maydon + Kasal/Ogohlantirgan/Oilaviy sabab/Sababsiz), "✓ Hammasi keldi", progress, hammasi belgilangach chiroyli "Yo'qlamani saqlash"; oylik jadval (%, sababli). Qulf olib tashlandi; Yo'qlama va Darsliklar kafellari oq ("Yangi" 28-noyabrgacha).
- Sinov: scratchpad `t120att.py` (20 API), `pw120.py` (26 brauzer: o'qituvchi telefon, rahbar kompyuter, admin telefon, WebKit tungi).
- Keyin: o'quvchi kartasida davomat, Excel, ota-onaga SMS (Eskiz shabloni kerak).

### v12.1 (2026-11-14) — backend: routers/attendance.py + index.html (v12.0 fayllari bilan birga yuklanadi)
- Admin/rahbar Yo'qlamaga kirganda avval **o'qituvchilar to'rtburchak kafellari** (`attTeacherTiles`, `.att-tile`: rangli aylana bosh harflar, ism, fan, holat "✓ 2/2 olingan" / "0/1 olinmagan" (to'q sariq nuqta) / "dars yo'q"); bosilsa → o'sha o'qituvchining guruhlari (`attPickTeacher`, "‹ O'qituvchilar"). Telefonda 3 ustun.
- **Admin/rahbar faqat bugun + oxirgi 3 kun** yo'qlama kiritadi/tuzatadi (`STAFF_EDIT_DAYS = 3`, `_can_edit`); eskisi faqat ko'rish ("🔒 3 kundan eski yo'qlamani o'zgartirib bo'lmaydi"). O'qituvchi — faqat bugun (o'zgarmadi).
- "Yangi" lenta olib tashlandi: Xarajatlar, o'qituvchi "O'quvchi qo'shish" va "Guruhlarim".
- Sinov: `t120att.py` (24), `pw120.py` (36).

### v12.2 (2026-11-14) — backend: routers/attendance.py + index.html (v12.0/12.1 fayllari bilan birga yuklanadi)
- **Davomat statistikasi:** `GET /api/attendance/stats?month=YYYY-MM|all&teacher_id` (o'qituvchi — faqat o'z guruhlari; admin/rahbar — hammasi, o'qituvchi filtri) → har o'quvchi: keldi, kelmadi, sababli, %, guruh/o'qituvchi; `GET /api/attendance/student-detail/{id}?month` → har bir kun (sana, hafta kuni, o'qituvchi, guruh, holat, sabab, kim kiritgan). Begona o'qituvchi — 403.
- Frontend: admin/rahbar kafellari oxirida firuza "📊 Statistika" kafeli; o'qituvchida guruhlar ustida "📊 Davomat statistikasi" kartasi (`attOpenStats`). Oy ‹ ›, "Oy bo'yicha / Barcha vaqt", jami (darslar, o'rtacha %, kelmaganlar), o'qituvchi chiplari, qidiruv, tartib (Ko'p qoldirgan / Davomat % / Ism). O'quvchi bosilsa oyna (`attStudentDetail`): 4 ko'rsatkich, Hammasi/Kelmagan/Kelgan, kunlar ro'yxati sabablari bilan, qo'ng'iroq.
- Sinov: `t122.py` (10 API), `pw122.py` (27 brauzer).

### v12.3 (2026-11-14) — backend: routers/salary.py + index.html
- **O'qituvchilar hisob-kitobi:** "O'quvchilar / To'lagan (shu oy) / To'lamagan" bosiladi (`.mini-stat.ts-tap`, "Ro'yxat ›") → oyna `openTeacherStudents(tid, f)`: 3 tab (sonlari bilan), qidiruv, har qatorda Familiya Ism, telefon(lar) (bosiladi), "qo'shdi: Rahbar/Admin/O'qituvchi • sana", guruh, manba, ✓ To'lagan (ulush) / ⏳ To'lamagan. API `GET /api/salary/teacher/{id}/students` (rahbar/admin, faqat o'qish) — `my_students`+`teacher_payments` bilan, overview sonlari bilan aynan mos (sinovda 18/18, 7/7).
- **Shisha (tomchi) menyular** (CSS oxirida "v12.3: SHISHA" bloki): bosh menyu, papka kafellari, o'qituvchi kafellari, yo'qlama kafellari — tiniq oq gradient, `backdrop-filter`, ichki yorug'lik/soya (bo'rtib turadi), `::before` mask bilan burchaklarda oq yaltiroq chegara, ikonka kichik shisha tomchi; sahifa foni yengil rangli dog'lar (shisha ko'rinsin). Tungi rejim / o'qituvchi Tungi-Shaffof — to'q shisha. PRO (qulf) kartalar o'zgarmadi. Telefonda kafellar bir xil balandlikda (`margin 0`).
- Sinov: `pw123.py` (12) + skrinshotlar (rahbar/admin kompyuter-telefon, o'qituvchi 3 mavzu).

### v12.4 (2026-11-14) — faqat index.html
- Shisha kafellar **tiniq** qilindi (Sukhrob: "xira bo'lmasin"): blur 16px → 4px, lavanda tuman va binafsha ichki soya olib tashlandi, faqat oq yaltiroqlar; ikonka ham tiniq oq tomchi. To'q shisha blur 5px.

### v12.5 (2026-11-14) — SERVERGA YUKLANGAN (12.0–12.5 hammasi, md5 8b92f492…) — ARXIV (markazdan ketganlar). backend: models, main, schemas, student_links, routers/students, teacher_self, payments, dues, backup + index.html
- O'quvchi **o'chirilmaydi** — "🚪 Markazdan ketdi" (Jami o'quvchilar jadvalida 🚪, o'quvchi kartasida) → sabab (ixtiyoriy, tez tugmalar) → arxiv. `students.archived_at/archived_by/archive_reason/returned_at` (ms), jadval `student_archive_log` (action archive|restore, at, by, reason, teachers JSON — o'sha paytdagi o'qituvchilari).
- Arxivdagi o'quvchi: `GET /api/students` da yo'q, `my_students` (o'qituvchi ro'yxati, hisob-kitob sonlari, yo'qlama) da yo'q, qarzdorlar (`/api/dues`) va takroriylar bannerida yo'q, **to'lov qabul qilinmaydi** (400), o'qituvchi biriktira olmaydi; shu ism+telefon bilan qayta qo'shilsa 409 `archived_student` → "Arxivdan qaytarasizmi?". To'lovlar, ulushlar, kassa, o'qituvchi balansi **o'zgarmaydi** (sinovda tekshirilgan).
- API: `POST /api/students/{id}/archive {reason}`, `POST /{id}/restore`, `GET /api/students/archived`, `GET /{id}/profile` (to'lovlar + ulushlar, oylar, kimlarda o'qigan (snapshot+to'lov+hozirgi), qarzlar, tarix) — rahbar/admin.
- **Qaytarish:** yana Jami o'quvchilarda (`returned_at`, "↩️ qaytdi sana" belgisi), to'lov qabul qilinadi; repetitorning teacher/subject/group va `student_teachers` tozalanadi — eski o'qituvchida avtomatik chiqmaydi; `my_students`/`teacher_payments` da **returned_at dan oldingi to'lovlar hisobga olinmaydi** (yangi to'lov ulushi kimga bo'linsa — o'shanda chiqadi, yoki o'qituvchi o'zi biriktiradi).
- Frontend: O'quvchilar papkasida "🗄️ Markazdan ketganlar" (`#archiveSection`, `openArchiveSection`, `renderArchive`): 3 ko'rsatkich, qidiruv, qatorlar (ism, telefon, sabab, arxivga tushgan sana/soat/kim, jami to'lov); bosilsa `openArchivedCard` (qachon ketgan, telefon, jami, qo'shgan, oylar chiplari, kimlarda o'qigan, to'lovlar, tarix, "↩️ Arxivdan qaytarish" → `askRestoreStudent`). Zaxira (backup) arxiv maydonlarini ham saqlaydi.
- Sinov: scratchpad `t125.py` (21 API, kassa/balans har qadamda), `pw125.py` (17 brauzer), t109/t122 qayta o'tdi. Mac zaxirasi: `_backup_2026-11-14_v12.4/`.

### v12.6 (2026-11-14) — SERVERGA YUKLANGAN — MAKTAB YO'QLAMASI (eshik oldida). backend: models, main, routers/school_attendance.py (yangi) + index.html
- Yo'qlama endi **faqat admin va rahbarda**, **faqat maktab o'quvchilari** (type='school', arxivda emas), fan/o'qituvchi/guruhsiz. O'qituvchi kabinetidan Yo'qlama kafeli olib tashlandi (eski guruh yo'qlamasi kodi/jadvallari qoldi, ishlatilmaydi).
- Jadval `school_attendance` (student_id+date unique, status present|late|absent, time HH:MM, deadline, reason, marked_by/at); `settings.att_deadline` (standart 08:30). "Keldi" → shu zahoti Toshkent vaqti; vaqt ≤ deadline = **vaqtida** (yashil chiroq), keyin = **kechikdi** (sariq chiroq, necha daqiqa/soat); "Kelmadi" → qizil chiroq + sabab (ixtiyoriy: Kasal/Oilaviy sabab/Ogohlantirgan/Sababsiz/o'zi yozadi). Belgini bosib vaqtni tuzatish yoki olib tashlash. O'tgan kun (≤3 kun) — vaqtni qo'lda kiritadi; eskisi faqat ko'rish.
- API `/api/school-att`: GET/PUT `/settings` (PUT faqat rahbar), GET `/day?date`, POST `/mark {student_id, status: came|absent|clear, date?, time?, reason?}`, POST `/absent-rest` (qolganlarni "kelmadi"), GET `/stats?month`, GET `/student/{id}?month`.
- Frontend `SAT`/`satOpen` (`#satRoot`): ko'k hero (kun ‹ ›, "Hozir" soat, "⏰ Kelish vaqti" — rahbar bosib o'zgartiradi), 5 ta filtr-karta (Jami/Vaqtida/Kechikdi/Kelmadi/Belgisiz) + rangli chiziq, katta qidiruv (belgilangach tozalanadi — eshikda keyingi o'quvchi), sinf chiplari, qatorlarda yonib turuvchi chiroq (LED), "Keldi"/✗. **📄 PDF** (`satPdf`, jsPDF 2.5.1 + autotable 3.8.2 cdnjs, kerak bo'lganda yuklanadi): sarlavha, 5 ko'rsatkich, jadval — kechikkanlar (vaqt bo'yicha), kelmaganlar (sabab), belgisizlar; lotin-1 bo'lmagan harflar `satLat`. **📊 Statistika** oy bo'yicha + o'quvchi kunlari oynasi.
- O'quvchi tahrirlash oynasi (`openStudentEditor`) pastida ham "🚪 Markazdan ketdi".
- Sinov: scratchpad `t126.py` (20 API), `pw126b.py` (23 brauzer, PDF yuklanishi). Mac zaxirasi: `_backup_2026-11-14_v12.5/`.

### v12.7 (2026-11-14) — SERVERGA YUKLANGAN (md5 74256c1e…) — faqat index.html (v12.6 backend bilan birga)
- Adashib "Kelmadi" belgilangan o'quvchida "✓ Keldi" bosilsa — darhol hozirgi vaqt emas, **kelgan vaqtini so'raydi** (oyna, standart — hozir), keyin vaqtida/kechikdi qayta hisoblanadi.
- **PDF ota-onalar guruhi uchun**: jami va belgisizlar YO'Q. Sarlavha (maktab, sana, o'ng tomonda "Dars boshlanish vaqti"), 2 bo'lim: "Kechikib kelganlar" (#, F.I., sinf, kelgan vaqti, necha kechikdi — sariq) va "Darsga kelmaganlar" (#, F.I., sinf, sababi / "Sababi aytilmagan" — qizil).

### v12.8 (2026-11-14) — SERVERGA YUKLANGAN (md5 f4bf1c5b…) — YO'QLAMACHI + LOGIN/PAROLNI KO'RISH. backend: models, main, auth, student_links, routers/auth, teachers, subjects, school_attendance + index.html
- **Yangi rol "Yo'qlamachi"** (`auth.ROLE_ATT`, bitta login). Rahbar: Sozlamalar → "📋 Yo'qlamachi logini" (`#attUserSection`, `loadAttUserPanel`): yaratish / ko'rish / o'zgartirish / o'chirish. API `GET/POST/DELETE /api/auth/att-user` (rahbar). Kirganda faqat `#attPortal` (oq tepa panel: logo, "🔐 Login va parol", "🚪 Chiqish") — `#satRoot` shu yerga ko'chiriladi (`initializeAttPortal`, chiqishda `closeAttPortal` qaytaradi). `/api/school-att/*` → `require_attendance` (rahbar/admin/yo'qlamachi; kelish vaqtini faqat rahbar). Boshqa hamma API 403 (teachers/subjects ro'yxati ham).
- **Parolni ko'rish:** `users.password_enc` — AES-GCM, kalit `backend/pw_secret.key` (**o'chirmang** — o'chsa hamma parollar "hali kirmagan" bo'lib qoladi, kirish ishlayveradi). `auth.set_password()` xesh + shifrlangan nusxa. Eski foydalanuvchilarniki — birinchi to'g'ri kirishda saqlanadi.
- **Login va parol kafellari** (`credHubMount(id)`, `.ch-*`): "👁️ Login va parolimni ko'rish" (`GET /api/auth/my-credentials`), "🔄 Login va parolni almashtirish"; rahbarda + "👥 Xodimlarim login paroli" (`GET /api/auth/staff-credentials`: admin, yo'qlamachi, o'qituvchilar, xodimlar; qidiruv, 👁️/📋, ✏️ → `PUT /api/auth/users/{id}/credentials`). Joylari: Sozlamalar → Mening login va parolim (`#credHub`), o'qituvchi/xodim Profil → Login va parol (`#tpCredHub`), yo'qlamachi oynasi (`#apCredHub`).
- **Olib tashlandi:** "🔢 Tiklash kodi" (tugmalar, oyna, `/teachers/{id}/reset-code`, `/auth/reset-with-code`); "Parolni unutdingizmi?" da "O'qituvchiman" — endi "rahbardan so'rang" yozuvi + rahbar maxfiy parol formasi. O'qituvchilar hisob-kitobidagi takroriy sarlavha ("O'qituvchilar bo'yicha hisob-kitob") olib tashlandi.
- Sinov: scratchpad `t128.py` (42 API, hisob-kitob o'zgarmagani), `pw128.py` (59 brauzer: yo'qlamachi telefon/kompyuter/WebKit iPhone, rahbar, o'qituvchi 2 mavzu). Mac zaxirasi: `_backup_2026-11-14_v12.7/`.

### v12.9 (2026-11-14) — SERVERGA YUKLANGAN (md5 c2df12ab…) — faqat index.html: TELEFON RAQAMI MAJBURIY
- O'qituvchi/xodim kabinetiga kirganda `dash.phone` bo'sh bo'lsa — yopilmaydigan to'liq ekran oyna `#phoneGate` (`pgShowGate`): "+998" + raqam (avto-format "90 123 45 67", `+998...` yozsa ham to'g'ri, operator kodi tekshiruvi `PG_CODES`), "Davom etish" → "Raqamingiz to'g'rimi?" → "✅ Ha, to'g'ri" → `PUT /api/teacher/phone` → "Rahmat! ✅" → kabinet ochiladi. Faqat "🚪 Chiqish" bor. Raqam bo'lsa — umuman chiqmaydi; profilda raqamni o'chirsa — yana chiqadi. Admin/rahbar/yo'qlamachida yo'q (ularda teachers.phone yo'q).
- "Parolni unutdingizmi?" dan "O'qituvchi, admin yoki xodimmisiz? … rahbardan so'rang" yozuvi olib tashlandi.
- Kod orqali parol tiklash (SMS/Telegram) — Sukhrob: "keyinchalik Eskiz bilan". Raqam oldindan saqlangan bo'lishi shart (tiklash paytida yangi raqam qabul qilinmasin — xavfsizlik).
- Sinov: scratchpad `pw129.py` (28: telefon, kompyuter, WebKit iPhone).

### v13.0 (2026-11-14) — SERVERGA YUKLANGAN (md5 5adddcf8…) — CHAT (Telegram uslubida) + menyular. backend: models, main, security, routers/chat.py (yangi) + index.html, sw.js
- **Chat** (`routers/chat.py`, prefix `/api/chat`, rollar: rahbar, admin, O'qituvchi (o'qituvchi+xodim); yo'qlamachi — 403). Jadvallar `chat_threads` (kind direct|group, key `d:min:max` / `g:all`, last_msg_id), `chat_members` (last_read_id — o'qildi belgisi), `chat_messages` (soft delete); `users.last_seen` (onlayn < 70 s).
- API: `GET /state` (ro'yxat: guruh + hamma kontaktlar, o'qilmaganlar), `GET /unread` (belgi), `POST /open {user_id}`, `GET /thread/{id}?after|before`, `POST /thread/{id}/send {chat_text}`, `POST /thread/{id}/read {last_id}`, `DELETE /message/{id}` (faqat o'ziniki), `GET /user/{id}` (faqat ism/lavozim/onlayn). **Suhbatni faqat a'zolar ko'radi** (rahbar ham boshqalarning yozishmasini ko'ra olmaydi). Telefon/login/summalar hech qayerda yo'q. `chat_text` maydoni `<` `>` tekshiruvidan ozod (security.SKIP_KEYS) — ekranda doim escape.
- Yangi xabar → qabul qiluvchilarga Web Push (BackgroundTasks, `kind:'chat'`); sw.js chat push'ni alohida ko'rsatadi, bosilsa `open-chat` xabari / `/?chat=ID`.
- Frontend `#chatApp` (`chatOpen`, `CX`): to'liq ekran; kompyuterda chap ro'yxat + o'ng suhbat, telefonda ro'yxat → suhbat. Rasmli fon (SVG naqsh: kitob, qalam, yulduz…), pufakchalar (o'ziniki yashil), sana ajratgichlari, "O'qilmagan xabarlar", ✓ / ✓✓, guruhda yozgan ism + avatar, profil oynasi, nusxa olish / o'chirish, ↓ tugma, eski xabarlar yuqoriga surilganda yuklanadi. Ovozlar WebAudio bilan (yuborish "tiq", kelganda "din-din"). So'rovlar: ochiq suhbat 2,5 s, ro'yxat 4 s, belgi 15 s.
- **Menyular:** rahbar pastki menyusi: Asosiy • 💬 Chat • [To'lov] • O'chirish • Sozlama (Sozlama → `openSettingsHome()`, sozlama kafellari); admin: Asosiy • 💬 Chat • … ("Tarixim" o'rniga); o'qituvchi/xodim: Asosiy • O'quvchilar • 💬 Chat • Hisob • Profil. Bosh menyuda "💬 Chat" kafeli (`#menuChat`, "Yangi" 28-noyabrgacha) va yon menyuda (qizil son bilan). Qizil belgi `[data-cx-badge]`.
- Papka ichidagi va Sozlamalar kafellari endi bosh sahifadagi kafellar bilan bir xil o'lchamda (oq panel olib tashlandi).
- Sinov: scratchpad `t130.py` (23 API — maxfiylik, o'qildi, hisob-kitob o'zgarmagani), `pw130.py` (18 brauzer: rahbar kompyuter ↔ Vali telefon, guruh, tungi rejim, pastki menyular). Mac zaxirasi: `_backup_2026-11-14_v12.9/`.
- Kelajakda: o'quvchilar kabineti yaratilganda — o'quvchilarni ham chatga qo'shish.

### v13.1 (2026-11-15) — SERVERGA YUKLANGAN (md5 cde8e421…) — CHAT yaxshilandi. backend: models, main, routers/chat.py + index.html
- **Klaviatura (iPhone/Android):** `#chatApp` doim ko'rinadigan qismga moslanadi — `visualViewport` (iOS: `--cxh` balandlik, `--cxt` siljish), viewport meta'da `interactive-widget=resizes-content` (Android). Chat ochiq bo'lsa `body.cx-lock` (position:fixed, scroll saqlanadi), tortib yangilash o'chadi. Yuborish tugmasi klaviaturani yopmaydi. Xabarlar **pastdan boshlanadi** (`.cx-wrap { margin-top:auto }`).
- **Tepa panel** Telegram iOS kabi: chapda shisha doira "‹", o'rtada shisha kapsula (ism + "onlayn" / "oxirgi marta: kecha 22:14 da"), o'ngda avatar. Yozish maydoni ham shisha.
- **Onlayn/chiqdi:** ilova fonga o'tganda/yopilganda `POST /api/chat/away` (keepalive) — darhol "oxirgi marta: HH:MM da" (server xotirasida `_away`), qaytganda yana onlayn.
- **Javob (reply):** `chat_messages.reply_to_id`; xabar menyusi "↩️ Javob berish", telefonda xabarni chapga surish, kompyuterda 2 marta bosish; yozish ustida iqtibos paneli; pufakchada iqtibos — bosilsa asl xabarga o'tib yoritadi. Boshqa suhbatdagi xabarga javob berib bo'lmaydi.
- **Kimlar o'qidi:** `GET /api/chat/message/{id}/reads` (faqat o'z xabari) — guruhda o'z xabarini **bosib tursa** (yoki menyudan) "✓✓ O'qiganlar / ✓ Hali o'qimaganlar" ro'yxati.
- **O'z profilim:** ro'yxat tepasidagi o'z avatarim → `GET /api/chat/me` (ism, lavozim, telefon — faqat o'ziga). Boshqalarning profilida telefon yo'q.
- **Ro'yxat "Chatlar":** faqat yozishilgan suhbatlar + 📌 Umumiy guruh. Yangi suhbat — ✏️ tugmasi (barcha xodimlar, qidiruv bilan). Qidiruvda yozishmaganlar ham chiqadi.
- Sinov: scratchpad `pw131.py` (34: Chrome kompyuter ↔ telefon, WebKit iPhone, klaviatura simulyatsiyasi), `vv131.py` (iOS visualViewport), `t131.py` (9 API), `t130.py` (23).

### v13.2 (2026-11-15) — SERVERGA YUKLANGAN (md5 df9015bf…) — CHAT: tungi shisha, pastki menyu, surib orqaga. backend: routers/chat.py + index.html
- **Chat doim tungi va shaffof shisha** (Telegram dark): to'q gradient + naqshli fon, `.cx-gl` shisha elementlar, o'ziniki yashil pufakcha. Chat ochiq paytda `#editModal`/`#actionSheet` ham tungi shisha (`body.cx-lock ...`).
- **Klaviatura:** ilova balandligi doim to'liq ekran (`--cxh` = innerHeight), fon `.cx-wall` butun ekran — **joyida turadi**; klaviatura balandligi `--kb` (innerHeight − visualViewport.height) — faqat xabarlar va yozish maydoni ko'tariladi, tepa panel joyida. Viewport meta'dan `interactive-widget` olib tashlandi (standart resizes-visual). Chat ochiq paytda orqadagi sahifa `inert` (`cxInert`) — iPhone'dagi ↑↓ o'qlari bo'sh. **iPhone'ning ↑ ↓ ✓ panelini sayt olib tashlay olmaydi** (faqat App Store ilovasi).
- **Chapdan surib orqaga** (telefonda, ekran chetidan 30 px): suhbat barmoq bilan birga suriladi, ro'yxat orqada ko'rinadi; 1/3 dan ko'p yoki tez surilsa — orqaga. **Tarix:** chat ochilganda `history.pushState` (1 — chat, 2 — suhbat) — Android "orqaga" tugmasi / Safari surishi ham ishlaydi (`popstate`).
- **Pastki menyu** (shisha kapsula): Kontaktlar (barcha xodimlar: Rahbariyat / O'qituvchilar / Xodimlar, onlayn holati bilan) • Chatlar (yozishilganlar, o'qilmaganlar soni) • Sozlamalar (o'z akkauntim: ism, lavozim, telefon; 🔔 ovozlar o'chirib-yoqish `localStorage.oxmed_chat_sound`; chatdan chiqish). ✏️ tugmasi → Kontaktlar.
- **Xodim profili:** telefon raqami (📞 Qo'ng'iroq tugmasi), "Qaysi fan o'qituvchisi" / lavozimi, 💬 Xabar yozish. `GET /api/chat/user/{id}` endi `phone` qaytaradi (Sukhrobning iltimosi).
- Yo'qlama va SMS kafellaridan "Yangi" lentasi olib tashlandi.
- Sinov: scratchpad `pw132.py` (18: kontaktlar, profil, klaviatura simulyatsiyasi — fon joyida, chapdan surish, telefon "orqaga" tugmasi, sozlamalar, WebKit iPhone).

### v13.3 (2026-11-15) — SERVERGA YUKLANGAN — CHAT: bosib turish menyusi, reaksiya, tahrir, qadash, uzatish, rasm. backend: models, main, routers/chat.py + index.html
- **iPhone tuzatildi:** pastdagi oq chiziq va klaviatura ustidagi bo'shliq — balandlik endi `position:fixed` o'lchagich (`#cxProbe`) bilan; klaviatura yo'q bo'lsa `.cx` top:0 bottom:0 (butun ekran), bor bo'lsa ko'rinadigan qismga + `--kb`.
- **Bir bosish — hech narsa; bosib turish (420 ms) yoki o'ng tugma** → Telegram menyusi (`cxCtx`, `#cxCtx`): fon xiralashadi, xabar ajralib turadi, tepada reaksiyalar (🤝😁❤️🤣🔥👍😢 + ⌄ 👏😮🙏💯🎉), pastda: Javob yozish, Nusxalash, Tahrirlash (o'ziniki), Qadash / bekor qilish, Uzatish, Kimlar o'qidi (guruhda o'ziniki), O'chirish (o'ziniki). Chapga surish — javob (avvalgidek), 2 marta bosish (kompyuter) — javob.
- Backend: `chat_reactions` (har kishi bitta xabarga bitta emoji; `POST /message/{id}/react`), `PUT /message/{id}` (tahrir, `edited_at`, "tahrirlangan"), `POST /thread/{id}/pin` (`pinned_msg_id`, tepada "📌 Qadalgan xabar" paneli), `POST /forward` (`forwarded_from`, "↪️ Uzatildi: X"; faqat o'zi ko'ra oladigan xabar). `chat_threads.rev` — tahrir/o'chirish/reaksiya/qadashda o'zgaradi, suhbatdoshda 2,5 s ichida avtomatik yangilanadi.
- **Profil rasmi:** `users.avatar_data` (320×320 JPEG data URL, ~30 KB), `avatar_v`; `POST/DELETE /api/chat/avatar`, `GET /api/chat/avatar/{id}`; kontaktlarda `av` versiyasi. Frontend keshi `localStorage['oxav:ID']`. Sozlamalar → 📷 Rasm qo'yish / almashtirish / 🗑️ o'chirish (ixtiyoriy).
- **Chatda tortib yangilash** (ro'yxatlar: Chatlar/Kontaktlar) — aylanuvchi shisha doira.
- **Bildirishnomalar (hamma joyda):** tepada o'rtada, shisha kapsula, bittadan; oddiy 2,8 s, xato 4,5 s; "Xush kelibsiz" 1,8 s (`showNotification(msg, type, ms)`). Telefonda tortib yangilaganda alohida "Yangilandi" chiqmaydi (doira o'zi aytadi), kompyuterdagi ⟳ — tepada o'rtada.
- Silliqlik: suzuvchi sana yorlig'idan og'ir blur olib tashlandi, pufakchalar GPU qatlamida.
- Sinov: scratchpad `pw133.py` (15), `t133.py` (17 API, hisob-kitob o'zgarmagani), pw132 (18), pw129 (28) qayta o'tdi. Mac zaxirasi: `_backup_2026-11-15_v13.2/`.

### v13.4 (2026-11-15) — SERVERGA YUKLANGAN (13.3 bilan) — faqat index.html: TUNGI REJIM, YANGI PASTKI MENYU
- Bosh sahifadan "💬 Chat" kafeli olib tashlandi (pastki menyuda bor); kompyuter yon menyusida Chat qoladi (`renderSidebar` — Sozlamalar guruhidan oldin).
- **Pastki menyu (telefon, ikkala rejim):** kapsula (shisha), 5 ustun, tanlangan tugma ostida siljiydigan "pill" (`.nb-drop`), To'lov — gradient doira, yozuvlar bir qatorda. Selektorlar `#mobileBottomNav.mobile-bottom-nav` + `html:is(...)` — eski qoidalardan kuchli.
- **Sozlamalar → 🌗 Ko'rinish rejimi** (`openThemePicker`, `setUiMode('light'|'dark')`, `localStorage.oxmed_ui_mode`) — rahbar va admin, telefon va kompyuter.
- **Tungi rejim (CSS "v13.4: TUNGI REJIM"):** to'q fon, bo'limlar va kafellar toza shaffof shisha (rangli yonish YO'Q — Sukhrob: "svet kerak emas"); Umumiy jadval to'q (qatorlar, sarlavhalar, jami), chiplar/yorliqlar shaffof rangli; telefon `--m-*` o'zgaruvchilari tungi uchun aniqlangan (orqaga tugmasi, chiziqlar, maydonlar). **Qizil/yashil yozuvlar yorqin:** `markRG()` (faqat tungi rejimda, `#dashboard` MutationObserver) computed rang bo'yicha `rg-red` (#ff4d5e) / `rg-green` (#2ff07c) qo'yadi.
- **Chat:** profil faqat **rasmga** bosilganda ochiladi (`.cx-avtap`); qatorning boshqa joyi — suhbat (Kontaktlar ham). Tepadagi kapsula endi profil ochmaydi; guruh rasmi → a'zolar (`cxGroupInfo`).
- Sinov: scratchpad `thp134.py` (8), `nav134.py` (4), pw133 (15), pw132 (18).

### v13.5 (2026-11-15) — SERVERGA YUKLANGAN (md5 b04c1200…) — faqat index.html: TUNGI REJIM HAMMA JOYDA, STANDART TUNGI
- **Standart — tungi rejim** (`<head>` skripti: `oxmed_ui_mode !== 'light'` bo'lsa `data-ui="dark"`). Foydalanuvchi Sozlamalar → Ko'rinish rejimi'da "Kunduzgi"ni tanlasa — doim oq (shu qurilmada).
- **`markDark()`** (oldingi markRG o'rniga, faqat tungi rejimda): `#dashboard`, ochiq oynalar, `#attPortal` ichida — och fonli bloklar → `dk-bg` (shaffof shisha), to'q fonda qolgan qora yozuvlar → `dk-ink` (#e8ecf6), qizil/yashil → `rg-red`/`rg-green` (yorqin). Yashirin panellar ham oldindan tekshiriladi. MutationObserver (chat o'zgarishlari va o'z sinflari hisobga olinmaydi). CSS selektorlari `:is(#dashboard, …, .modal)` — ID kuchida (`#settingsSection .set-card` kabi qoidalardan ustun). Natija: Sozlamalar panellari, O'qituvchilar va guruhlar, Hisobotlar, "Qanday ishlaydi?", SMS sozlamalari, O'quvchini o'chirish "Diqqat!", To'lovni tahrirlash oynasi — hammasi tungi shisha, yozuvlar ko'rinadi. Tungi rejimda select/input/textarea ham to'q.
- **Chiqish** tugmasi tungi rejimda: qizil shaffof fon + och qizil yozuv (telefonda ko'rinmay qolardi).
- **Kompyuter (≥769px, hover):** menyu/papka/sozlama kafeli ustiga borilganda 7px ko'tariladi va qizil yonadi; bosilganda yashil yonadi (`.tile-go`), 240 ms dan keyin bo'lim ochiladi (document capture click).
- Sinov: scratchpad `fix135.py` (rasmlardagi 8 joy × kompyuter/telefon), `hov135.py`, pw133/pw132/thp134/pw129 qayta o'tdi.

### v13.6 (2026-11-15) — SERVERGA YUKLANGAN (md5 159d9ede…) — faqat index.html: HAMMA BIR MARTA TUNGIGA
- `<head>` skripti: `localStorage.oxmed_ui_reset !== '13.6'` bo'lsa — `oxmed_ui_mode = 'dark'` qilinadi va belgi qo'yiladi (oldin oq tanlaganlar ham bir marta tungiga o'tadi). Keyin foydalanuvchi tanlovi (Kunduzgi/Tungi) doimiy saqlanadi. Yana hammani majburan o'tkazish kerak bo'lsa — belgi qiymatini o'zgartirish kifoya.
- Sinov: scratchpad `reset136.py` (4).

### v13.7 (2026-11-15) — SERVERGA YUKLANGAN — faqat index.html: O'QITUVCHI/XODIM KABINETI — STANDART "SHAFFOF"
- `initializeTeacherPortal`: `localStorage.oxmed_teacher_theme_reset !== '13.7'` bo'lsa — `oxmed_teacher_theme = 'glass'` (hammasi bir marta Shaffofga o'tadi), keyin o'z tanlovi (Yorug'/Tungi/Shaffof) saqlanadi. Standart (tanlov yo'q) — `glass`.
- Sinov: scratchpad `tth137.py` (4).

### v13.8 (2026-11-15) — SERVERGA YUKLANGAN (md5 6b794418…) — faqat index.html: KOMPYUTERDA YON MENYUNI YASHIRISH (☰)
- `#sbToggle` (`#dashboard` ichida, position:fixed, faqat ≥1100px): menyu ochiq — "OLMOS XATAMOV" yonida; bosilsa `toggleSidebar()` → `.dashboard.sb-off` (grid ustuni 0 ga silliq, menyu chapga suriladi), tugma chap yuqori burchakka o'tadi; yana bosilsa qaytadi. `localStorage.oxmed_sb_off` — eslab qolinadi. Keyin `resize` hodisasi (jadval yangi kenglikka moslashadi). Telefonda yo'q.
- Yon menyu sarlavhasi: "OLMOS XATAMOV" bir qatorda, ostida "maktabi" (avval "O'quv markaz boshqaruvi"); ☰ 32px, sarlavha yonida.
- Sinov: scratchpad `sb138.py` (6).

### v13.9 (2026-11-15) — SERVERGA YUKLANGAN (md5 876136ca…) — backend: routers/payments.py (+ schemas/models izohlari) + index.html: TERMINAL TO'LOV USULI, O'RNATISH BANNERI
- **To'lov usuli "terminal"** (plastik karta terminali): backend `PAY_METHODS = ("naxt","click","terminal")` (POST va PUT). Frontend yordamchilari `PAY_M`, `pmKey`, `pmOf(m)` (t/ic/cls/sum/badge), `pmBadge`, `pmSums(list)` — barcha joyda: To'lov kiritish, tahrirlash oynasi (`#peMethod`), Umumiy jadval filtri (`#btMethod`) va "🏧 Terminal" kartasi, jadval/telefon kartochkasi belgisi, Excel, To'lovlar tarixi statistikasi ("Naqd / Click / Terminal"), telefon ro'yxati, o'quvchi kartasi, takroriy to'lov oynasi. Rangi — firuza (`.pill.terminal`, `.badge-term`). **Kassa/ulushlar usulga bog'liq emas** — o'zgarmadi (sinovda tekshirildi).
- **"Ilovani o'rnating" banneri:** ilova o'rnatilgan bo'lsa (standalone) — hech qachon; o'rnatilmagan bo'lsa — faqat BIRINCHI kirishda (`localStorage.oxmed_install_banner`: yo'q → 'shown' + shu sessiya; keyingi kirishlarda yashirin); ✕ yoki `appinstalled` → 'off' (hech qachon). Yon menyu/Sozlamalardagi "O'rnatish" tugmasi qoladi.
- Tungi rejim: to'q fonda qolgan **rangli** yozuvlar endi oqarmaydi — rangi saqlanib yorqinlashadi (`dk-lift`, brightness 1.75); kulrang/qora yozuvlar — `dk-ink`.
- Sinov: scratchpad `t139.py` (7 API), `pw139.py` (9), fix135. Mac zaxirasi: `_backup_2026-11-15_v13.8/`.

### v13.10 (2026-11-15) — SERVERGA YUKLANGAN (md5 5e695fe5…) — faqat index.html: TERMINAL — SARIQ
- Terminal orqali qabul qilingan to'lov belgisi sariq: `.pill.terminal`, `.m-chip.terminal`, `.badge-term` (kunduzgi: #fef08a fon / #854d0e yozuv; tungi: sariq shaffof fon / #fde047). Umumiy jadvaldagi "🏧 Terminal" kartasi `.bt-sum.c-term` (avval `c-teal` — u "Xarajatdan keyin markazga" kartasida qoldi). Telefon To'lovlar tarixi statistikasida "🏧 Terminal" katagi (`.m-sum-term`), kompyuter statistikasida terminal summasi (`.term-y`) ham sariq. `DK_SKIP` ga qo'shilgan (tungi rejim rangni buzmaydi).
- Sinov: scratchpad `pw1310.py` (8). Mac zaxirasi: `_backup_2026-11-15_v13.9/`.

### v13.11 (2026-11-15) — SERVERGA YUKLANGAN (md5 d5c86344…; zaxira: backend/app_zaxira_13_10, index_eski_13_10.html, /root/oxmed_baza_zaxira_2026-11-15_v13_10.sql; serverda 29 ta to'lov — hammasi Noyabr 2026) — OYNING YILI (dastur o'zi) + ARXIV: BITIRGANLAR. backend: models, main, utils, schemas, ledger, routers/payments, dues, students, teacher_self, salary, sms, recycle, backup + index.html
- **Yilni odam tanlamaydi — dastur o'zi aniqlaydi:** `utils.auto_year(month, ts)` va frontend `autoYear(m)` — BIR XIL qoida: o'quv yili (Sentabr–Dekabr — boshlangan yil, Yanvar–Avgust — keyingi yil); natija 7 oydan ko'p oldinda bo'lsa — o'tgan yil, 8 oydan ko'p orqada bo'lsa — keyingi yil. 2026-noyabrda: Iyul–Dekabr → 2026, Yanvar–Iyun → 2027. 2027-noyabrda Noyabr → 2027 (2026-noyabr aralashmaydi).
- `payments.year`, `student_dues.year` (unique `ux_student_due_month_year` (student_id, month, year), eski `ux_student_due_month` o'chiriladi). Migratsiya `_backfill_years()` — yili yo'q qatorlarga kiritilgan vaqtiga ko'ra yil qo'yadi (summa/ulush/oy o'zgarmaydi). `POST/PUT /api/payments`, `PUT /api/dues` — ixtiyoriy `year` (berilmasa auto_year; joriy yildan ±2). Takroriy to'lov tekshiruvi — oy + YIL. Qarz = due − shu oy+yil to'langan.
- O'qituvchi kabineti (`/teacher/dashboard`) — faqat joriy davr to'lovlari (`in_current_window`). Hisob-kitob sonlari (`/salary/overview`) — joriy oy + joriy yil. Hisob varag'i: "Noyabr 2026 oyi". Profil oylari: "Sentabr 2026" (xronologik).
- Frontend yordamchilari: `autoYear`, `ymParse` ('Noyabr' | 'Noyabr|2026' | '__all'), `pmIs(x, v)`, `inWin`, `ymOf`, `ymText`, `ymLabel`, `tsYM` (xarajat/oylik — vaqtidan), `winMonths()` (joriy 12 oy xronologik), `tabLabel` (boshqa yil bo'lsa yili bilan). To'lov kiritish oylari "Iyul 2026 … Iyun 2027" (`fillPayMonthSelect`), tarix/admin tarixi/xarajat tablari joriy davr bo'yicha, Umumiy jadvalda "O'tgan davr" guruhi (`Oy|Yil`), qarz oynasi va tahrirlash oynasi `Oy|Yil`, SMS to'lamaganlar, bosh sahifa "shu oy" — oy+yil. "Barcha oylar" — joriy davr; qarzlarda — hamma ochiq qarzlar (yili bilan). **Kassa, ulushlar, balanslar umumiy (yilga bog'liq emas) — o'zgarmadi.**
- **Arxiv:** menyuda "🗄️ Arxiv" → 2 kafel: **🎓 Bitirganlar** / **🚪 Markazdan ketganlar** (`arcKind`, `arcOpenKind`, `arcBack`). `students.archive_kind` ('left'|'graduated'; eski arxivdagilar 'left'), log action 'graduate'. `POST /api/students/{id}/archive {kind:'graduated', reason}`; `GET /api/students/archived?kind=` → `kind, added_at, first_payment, months[], months_count, teachers`. Bitirganlar: kelgan sana, bitirgan sana, necha oy o'qigan (oylar oralig'i), jami to'lov, telefonlar; karta (`openArchivedCard`) — 🎓 Bitirgan, Qachon kelgan, Necha oy o'qigan, oylar chiplari, o'qituvchilar, to'lovlar, tarix. "🎓 Bitirdi" tugmasi (`askGraduateStudent`): Jami o'quvchilar jadvalida, o'quvchi kartasida, tahrirlash oynasida. Qaytarish avvalgidek.
- **O'quv yili tanlagichi (faqat KO'RISH):** To'lovlar tarixi, admin tarixi, Umumiy jadval, Xarajatlar tepasida "📅 Joriy davr (2026–2027 o'quv yili) ▾" (`oyPick(anchor, where)`, `setViewOY`, `VIEW_OY`, `viewYear`, `oyList`, `curOY`). Tanlansa — o'sha o'quv yilining Sentabr–Avgust oylari (yili bilan), "Barcha oylar", Excel. Bo'lim qayta ochilganda (`showSection`) yana joriy davr. To'lov kiritish (`curWinMonths`), yangi to'lov/qarz oynasi, SMS, bosh sahifa (`curYM()`) — DOIM joriy davr.
- Sinov: scratchpad `t1311.py` (23 API — yil qoidasi, takror, qarz, tahrir, bitirganlar, kassa/balans o'zgarmagani), `pw1311.py` (14), `pw1311b.py` (11 — bitirdi jarayoni kompyuter+telefon), `pw1311c.py` (13 — soxta soat 2027-noyabr: o'tgan yil aralashmaydi, tanlagich bilan ochiladi), pw1310, pw139, t98. Mac zaxirasi: `_backup_2026-11-15_v13.10/`.

### v13.12 (2026-11-15) — SERVERGA YUKLANGAN (md5 9d2b36d8…) — XODIMGA XARAJATLAR (bozorchi), TELEFON "ORQAGA"SI, YO'QLAMACHI YANGILASH. backend: models, main, schemas, auth, routers/staff, routers/expenses, routers/teacher_self + index.html
- **Xarajat kiritish ruxsati** — faqat rahbar belgilagan xodimga (masalan Dilso'z, Bozorchi): `teachers.can_expenses` (standart FALSE). Rahbar: Xodimlar → ✏️ Tahrir → "🧾 Xarajatlarni kiritadi" (`#sfExp`, kartada "🧾 Xarajat kiritadi" belgisi). `auth.require_expense_user` — rahbar, admin yoki ruxsatli xodim; `/api/expenses` GET/POST/PUT/DELETE shu bilan (tiklash — faqat rahbar). Xodim **faqat o'zi kiritganlarini** ko'radi/tahrirlaydi/o'chiradi; kelajak sana yo'q, 62 kundan eski yo'q. `ExpenseOut.added_by_name` (rahbarda "kim kiritdi" — xodim ismi, `EX.names`). Xodim xarajati boshqa xarajatlar kabi kassadan ayiriladi.
- Kabinet: `/teacher/dashboard` → `can_expenses`; `#teacherPortal[data-exp="1"]` bo'lsa bosh sahifada "🧾 Xarajatlar" kafeli (`.tp-only-exp`) → tab `data-tab="expenses"` (`tpxOpen`, `TPX`, `tpxSave/Edit/Delete`): Nima olindi (qo'lda), Summa, Sana, Izoh; oy tugmalari (joriy davr), oy jami, ro'yxat ✏️/🗑️. Tez tugmalar YO'Q (Sukhrob: "o'zi qo'lda yozadi").
- **Telefonning "orqaga"si qadam-baqadam** (Android tugma/surish, iPhone surish): oyna → bo'lim → papka → bosh menyu → ilovadan chiqish. Asosiy sahifada bo'lmaganda tarixda bitta qo'riqchi `{oxg:1}` (`navTrap`, `navUntrap`, `oxIsRoot`, `popstate` → `goBack()` / `closeEditModal` / `setTeacherTab('home')` / `tpProfBack`). `showSection`, `openEditModal`, `openActionSheet`, `setTeacherTab` qo'riqchi qo'yadi; `showMenu`, oyna yopilishi, Asosiy tab — ortiqchasini olib tashlaydi. Chat o'z tarixini boshqaradi (`CX.on` bo'lsa tegilmaydi).
- **Yo'qlamachi tortib yangilaganda chiqib ketardi** (refreshAppData `fetchAllData` → 403 → logout). Endi yo'qlamachida faqat `satLoad`/`satOpenStats`; 403 yo'qlamachini chiqarmaydi.
- Sinov: scratchpad `t1312.py` (20 API — ruxsat, faqat o'ziniki, kassa o'zgarmagani), `pw1312.py` (19 — kabinet, orqaga 4 qadam, yo'qlamachi yangilash, o'qituvchi), pw132 (18 — chat tarixi), pw1311/pw1311c. Mac zaxirasi: `_backup_2026-11-15_v13.11/`.

### v13.13 (2026-11-15) — SERVERGA YUKLANGAN (md5 b26bfa5e…) — BITTA LOGIN + RUXSATLAR, QO'SHIMCHA (ADMINLIK) OYLIGI, BIRLASHTIRISH, YANGILASHDA JOYIDA QOLISH, RANG DARHOL. backend: models, main, schemas, auth, ledger, routers/teachers, staff, salary, teacher_self, payments, students, dues, bt_columns, sms + index.html
- **Ruxsatlar (bitta login):** `teachers.perms` JSON — `auth.PERM_KEYS` = pay (To'lov kiritish), hist (To'lovlar tarixi), bt (Umumiy jadval), students (O'quvchilar: qo'shish/tahrir/arxiv/bitirganlar), att (Yo'qlama), sms, exp (Xarajatlar; `can_expenses` bilan sinxron). `auth.user_perms(db, user)` (rahbar/admin — hammasi, yo'qlamachi — att), `auth.require_perm(*keys)`; `require_attendance` va `require_expense_user` shu orqali. Endpointlar: payments GET (pay|hist|bt), POST (pay|bt), PUT (pay|hist|bt, faqat o'zi kiritgani); students GET (pay|hist|bt|students|sms), POST/arxiv/qaytarish/arxivlar/takrorlar/birlashtirish (students), PUT (students|pay|bt|hist), profile (students|hist|bt|pay); dues GET/PUT; bt-columns GET + katak (bt); sms status/test/templates/bulk/batches/logs (sms). **Hech qachon berilmaydi:** kassa, xodimlar oyligi (/salary, /staff), sozlamalar, qayta tiklash, o'quvchi/to'lovni o'chirish, SMS sozlamalari.
- API: `GET/PUT /api/teachers/{id}/access` (rahbar) {perms, monthly_salary, salary_start, position} → shares_total, salary_total, owed. `/teachers`, `/staff`, `/salary/overview`, `/teacher/dashboard` → `perms`; overview/dashboard → `shares_total`, `salary_total`, `monthly_salary`, `position`.
- **Qo'shimcha (adminlik) oylik o'qituvchiga:** `ledger.ensure_staff_accruals` endi is_staff sharti yo'q (oylik + boshlanish oyi bo'lsa); `ledger.split_totals` → (ulush, oylik). Balans formulasi o'zgarmagan (ulush + hisoblangan oylik − berilgan + qaytarilgan). Ko'rinishi: kabinet tepasi "Ulush X + oylik Y − olingan", hisob varag'i va O'qituvchilar hisob-kitobi kartasida `.ledger-split` (👨‍🎓 O'quvchilardan / 💼 Oylik). Oylik 0 qilinsa — keyingi oylardan to'xtaydi; o'chirilgan oy (0 so'm) qayta yaratilmaydi.
- **Xodimni o'qituvchiga birlashtirish:** `POST /api/staff/{id}/merge {teacher_id}` — salary_accruals va teacher_payouts o'qituvchiga o'tadi, oylik/lavozim/telefon/ruxsatlar ham; o'qituvchidagi 0 so'mlik bir xil oy yozuvi olib tashlanadi; balans = ikkalasining yig'indisi (tekshiriladi, mos kelmasa bekor). Xodim yozuvi (va logini) o'chadi.
- **Frontend:** `PERM_DEF/PERM_ORDER`, `permChips`, `openAccessEditor(tid)` (🔑 Ruxsat — xodim kartasida ikonka, O'qituvchilar hisob-kitobida "🔑 Ruxsat va oylik"; ichida almashtirgichlar, qo'shimcha oylik, birlashtirish), `saveAccess`, `mergeStaffInto`. Xodim tahriridan "Xarajat kiritadi" olib tashlandi (endi Ruxsatda). Kabinetda "🔑 Rahbar ochib bergan bo'limlar" (`renderPermTiles`, `#tpPermWrap`).
- **Ruxsat rejimi** (`PERM`, `permLoad`, `permOpen(k)`, `permClose`): kafel bosilsa — kabinet yashirinadi, `#dashboard` faqat o'sha bo'lim bilan (`body.perm-mode`: yon menyu, pastki menyu, bosh menyu yashirin; `currentUser.role` vaqtincha 'Administrator' — faqat ekran uchun, server ruxsatni o'zi tekshiradi). Ma'lumot faqat ochilgan endpointlardan. Orqaga / "Orqaga" — kabinetga (`showMenu` → `permClose`). O'quvchilar papkasida "O'chirish" yo'q.
- **Yangilashda joyida qolish:** `navSave` (sessionStorage `oxmed_nav`: bo'lim, papka, qaytish, sozlama paneli, xodimlar ko'rinishi, arxiv turi, kabinet tabi, ruxsat bo'limi) va `navRestore` (`tryRestoreSession` dan keyin). `refreshAppData` ruxsat rejimida `permLoad` (403 chiqarib yubormaydi).
- **Rang darhol:** `markDark(root)` — MutationObserver qo'shilgan qismni o'sha zahoti (mikrovazifada, ekranga chiqishidan oldin) bo'yaydi; `setUiMode` — `html.theme-swap` (animatsiyalar o'chadi) + to'liq `markDark()` sinxron. `.sf-sw` DK_SKIP da.
- **iPhone qimirlamasin:** `html { overflow-x: hidden; overscroll-behavior: none }`, `body { overflow-x: clip }`, telefonda konteynerlar `max-width: 100vw`.
- **Sozlamalar → "Yo'qlamachi logini"** — faqat eski yo'qlamachi logini mavjud bo'lsa ko'rinadi (o'chirish uchun; yangi yaratib bo'lmaydi; `window.__attUserExists`). Yo'qlama endi 🔑 Ruxsat orqali.
- Sinov: scratchpad `t1313.py` (32 API — ruxsatlar, adminlik oyligi, birlashtirish, kassa/balans), `pw1313.py` (25 brauzer — ruxsat oynasi, kabinet kafellari, ruxsat rejimi, orqaga, yangilash/qayta yuklash, rang almashinuvi), pw1312 (19), pw132 (18), pw1311/1311c, t1312, t1311. Mac zaxirasi: `_backup_2026-11-15_v13.12/`.

### v13.14 (2026-11-15) — SERVERGA YUKLANGAN (md5 d78117e2…; GEMINI_API_KEY hali kiritilmagan bo'lishi mumkin) — 🎙️ OVOZLI YORDAMCHI (Google Gemini). backend: routers/ai.py (yangi), main.py + index.html
- Pastki o'ng burchakda 🎙️ tugma (`#aiFab`; telefonda pastki menyudan yuqorida; kirish sahifasida va chat ochiqligida yo'q). Panel `#aiPanel`: mikrofon (bosib gapirish, yana bosib to'xtatish, ko'pi bilan 20 s), matn maydoni, misollar. Ovoz brauzerda **WAV 16 kHz mono** ga aylantiriladi (`aiWavB64`, ScriptProcessor) — iPhone/Android/kompyuterda bir xil; ~20 s ≈ 0,9 MB (nginx 1 MB chegarasi).
- Backend `POST /api/ai/command {text|audio, mime, targets:[{k,t}], screen}` → Gemini **Interactions API** (`POST https://generativelanguage.googleapis.com/v1beta/interactions`, header `x-goog-api-key`, `Api-Revision: 2026-05-20`, `system_instruction`, `input` [audio + text], `response_format` JSON schema, `generation_config.thinking_level=minimal`, `store:false`); javob `steps[].type=model_output → content[].text`. Natija: `{action: open|find_student|fill_payment|fill_expense|search|none, target, query, month, amount, method, title, note, heard, reply}`; `open` faqat yuborilgan `targets` ichidan (aks holda none + "Bu bo'lim siz uchun ochiq emas"). `GET /api/ai/status` → available (+ model rahbarga).
- **Kalit:** serverdagi `backend/.env` → `GEMINI_API_KEY=...` (ixtiyoriy `GEMINI_MODEL`, standart `gemini-3.5-flash-lite`; `GEMINI_API_URL` — sinov uchun). Kalit brauzerga chiqmaydi. Limit: foydalanuvchiga daqiqasiga 12, kuniga 300. Google 429 → "AI limiti vaqtincha tugadi".
- **Xavfsizlik:** AI faqat buyruqni qaytaradi; bajarishni dastur qiladi (`aiExec`): bo'lim ochish (`aiTargets` — rol/ruxsatga qarab; ruxsat rejimida `permOpen`), o'quvchini topish (bitta — karta, ko'p — tanlash ro'yxati; o'qituvchida — o'z ro'yxatida qidiruv), to'lov/xarajat formasini to'ldirish (Saqlash tugmasi yashil yoritiladi `.ai-glow` — o'zi saqlamaydi), joriy sahifada qidirish. AI'ga bazadagi ma'lumot yuborilmaydi (faqat gap va bo'lim nomlari). Hech narsa saqlanmaydi/o'chirilmaydi.
- Bepul limit: Google raqamlarni hujjatda e'lon qilmaydi — AI Studio → Rate limit sahifasida loyiha bo'yicha ko'rinadi; model Free tier'da ekanini o'sha yerda tekshirish kerak.
- Sinov: scratchpad `mock_gemini.py` (soxta Interactions API), `t1314.py` (12 API), `pw1314.py` (16 brauzer — matn, to'lov/xarajat to'ldirish, soxta mikrofon bilan ovoz, telefon o'qituvchi, ruxsatsiz bo'lim).

### v13.15 (2026-11-15) — SERVERGA YUKLANGAN — 🕓 OXIRGI AMALLAR (harakatlar jurnali). backend: audit.py (yangi), routers/audit.py (yangi), models, main + rich yozuvlar: routers/payments, students, teacher_self, expenses, salary, staff, teachers, auth, webauthn_auth, school_attendance, dues, recycle + index.html
- **Nima:** tizimdagi HAR BIR o'zgarish — kim (ism, rol), nima, kimga, qachon (soniyasigacha), qurilma (iPhone • Safari), IP. Faqat rahbar ko'radi. 30 kun saqlanadi (`audit.KEEP_DAYS`), keyin o'zi o'chadi (soatiga bir marta tozalanadi).
- **Ikki qatlam:** `audit.AuditMiddleware` (BaseHTTPMiddleware) — `/api/` dagi har bir muvaffaqiyatli POST/PUT/DELETE (va sezgir GET: xodimlar parollari, backup) yoziladi; matn `audit.ROUTES` jadvalidan. `audit.note(title, cat, entity, entity_id, details, username, force)` — endpoint ichidan tushunarli matn (ContextVar'dagi lug'atga qo'shiladi). Yozilmaydi: `/api/chat`, `/api/push`, `/api/ai`, `/api/audit/seen|unread`, xato (≥400) so'rovlar (faqat `force` — masalan noto'g'ri parol bilan urinish). **Parollar hech qachon yozilmaydi.**
- **Batafsil yozuvlar:** to'lov kiritish/tahrir (Oldin→Keyin: summa, oy, usul, ulushlar)/o'chirish; o'quvchi qo'shish (admin/rahbar/o'qituvchi), tahrir (diff), arxiv/bitirdi/qaytarish/birlashtirish/o'chirish; o'qituvchi o'z ro'yxatiga qo'shish/chiqarish, guruh; xarajat kiritish/tahrir/o'chirish/tiklash; avans/oylik/qaytarish/o'chirish; xodim qo'shish/tahrir/o'chirish/birlashtirish, bonus, oylikni tahrir/bekor; o'qituvchi qo'shish/o'chirish/telefon/login/ruxsatlar; kirish (parol / barmoq izi), ⚠️ noto'g'ri parol urinishi, login-parol o'zgarishlari, maxfiy parol bilan tiklash; qarz; yo'qlama belgisi; qayta tiklash/butunlay o'chirish.
- Jadval `activity_log` (at, username, who, role, cat pay|stu|exp|sal|staff|login|set|sms|att|other, action, title, details JSON, entity, entity_id, ip, ua, status); `users.audit_seen_id`. API (rahbar): `GET /api/audit?cat&who&q&before_id&limit`, `GET /api/audit/who`, `GET /api/audit/unread` (rahbarning o'z amallari hisoblanmaydi), `POST /api/audit/seen {last_id}`, `DELETE /api/audit {ids}` (o'chirish ham yoziladi).
- **Frontend:** Sozlamalar kafellarida "🕓 Oxirgi amallar" ("Yangi" lenta 29-noyabrgacha) → `#auditSection` (`openAuditSection`, `AU`): kategoriya chiplari, qidiruv, "kim" filtri, kun bo'yicha guruhlar (Bugun / Kecha / sana), qatorda ikonka-rang, matn, kim • rol • qurilma, soat:daqiqa:soniya, "Yangi" yorlig'i; bosilsa tafsilot (kim, rol, qachon, qurilma, IP, Oldin/Keyin jadvali); **bosib turish** (480 ms) yoki "☑️ Belgilash" → tanlash rejimi, tepada "N ta tanlandi • Hammasini tanlash • 🗑️ O'chirish". "Yana yuklash" (100 tadan).
- **Qizil belgi** (`auPaint`, `.au-badge`): yangi amallar soni — bosh sahifadagi Sozlamalar kafeli, yon menyudagi Sozlamalar (va ichidagi Oxirgi amallar), telefonda pastki "Sozlama", "Oxirgi amallar" kafeli. Har 45 s va ilovaga qaytganda tekshiriladi (`auPoll`); sahifa ochilganda "ko'rildi" bo'ladi.
- **v13.16:** rahbar o'chirgan yozuvlar butunlay yo'qoladi — "o'chirdi" degan yangi yozuv qo'shilmaydi (`/api/audit` SKIP da, `skip()`); tasdiq matni yangilandi. Yuklash: backend/app/audit.py, routers/audit.py + index.html.
- Tuzatildi: o'qituvchining qo'shimcha (adminlik) oyligini tahrirlash/bekor qilishda javob 404 qaytarardi (`_get_staff`) — endi `_any_teacher`.
- Sinov: scratchpad `t1315.py` (23 API — kim/qachon, parol yozilmasligi, tahrir diff, filtr, qidiruv, belgi, o'chirish, kassa o'zgarmagani), `pw1315.py` (18 brauzer — belgilar, kafel, ro'yxat, tafsilot, filtr, bosib turib belgilash va o'chirish, telefon, admin uchun yopiq), t1311/t1312/t1314/t98/t139.

### v13.17 (2026-11-16) — YO'QLAMA: BIR KUN — BITTA KELISH VAQTI + "TAHRIRLANGAN". backend: models, main, routers/school_attendance + index.html
- **Xato (serverda ko'rindi):** kelish vaqti 08:10 bo'lsa ham 08:52 "vaqtida", 09:00 "8 daq kechikdi" chiqardi. **Sababi:** har bir yozuv belgilangan PAYTDAGI kelish vaqtini o'zida saqlab qolardi (`school_attendance.deadline`), qayta belgilanganda ham eski vaqt ishlatilardi; rahbar vaqtni o'zgartirsa "avval belgilangan yozuvlar o'zgarmaydi" edi → bir kunda ikki xil vaqt (08:52 va 08:10) aralashib ketgan.
- **Tuzatish:** `_day_deadline(db, date)` — bugun = rahbarning hozirgi sozlamasi, o'tgan kun = o'sha kun yozuvlarida eng ko'p uchragan vaqt. `_normalize_day` shu kunning hamma yozuvlarini bitta vaqtga keltirib, vaqtida/kechikdi ni qayta hisoblaydi (`_calc`: vaqt ≤ kelish vaqti — vaqtida). Chaqiriladi: kelish vaqti o'zgarganda (bugungi yozuvlar), `/day` ochilganda (eski aralash yozuvlar o'zi tuzaladi), `/stats` va `/student/{id}` da. Belgilashda doim kunning yagona vaqti. Kelish vaqti o'zgarishi jurnalga "08:52 → 08:10 (N ta qayta hisoblandi)" bo'lib yoziladi; belgini olib tashlash ham yoziladi.
- **"✎ tahrirlangan":** yangi ustunlar `edited_at, edited_by, orig_status, orig_time`. Mavjud yozuv o'zgartirilsa (vaqt, holat, sabab) yoki bugun vaqt qo'lda yozilsa — qatorda binafsha "✎ tahrirlangan • kim • soat" (`.sat-edtag`); bosilsa oynada "📝 Belgiladi: X" va "✎ Avval: 08:51 kechikdi • tahrirladi: Y • 10:08" (`satEditTxt`). Asl (birinchi) holat bir marta saqlanadi. Oddiy "Keldi" bosish — tahrir emas. O'quvchi kunlari oynasida ham belgi.
- Sinov: scratchpad `t1317.py` (21 API — 09:00→08:10 qayta hisob, chegara 08:10/08:11, tahrir tarixi, eski aralash yozuv o'zi tuzalishi, o'tgan kun, jurnal, kassa o'zgarmagani), `pw1317.py` (12 brauzer, telefon+kompyuter), t126 (20). Mac zaxirasi: `_backup_2026-11-16_v13.16/`.

### v13.18 (2026-11-16) — faqat index.html: KIRISH SAHIFASIDA QOR ❄️
- Faqat kirish sahifasida (dastur ichida yo'q; kirgandan keyin to'xtaydi — `MutationObserver` `#loginPage` style). Mavsum: **15-noyabr — 1-mart** (Toshkent); boshqa paytda sinash uchun `?snow=1`.
- Ikki canvas (`.lg-snow`, pointer-events:none — maydonlar/tugmalar avvalgidek bosiladi): `#lgSnowBack` (z 0, kartochka ortida mayda xira qor) va `#lgSnow` (z 3, katta parchalar + to'plangan qor). Shamol sekin o'zgaradi.
- **To'planish:** yuzalar `DEFS` — logo (rasmning shaffof bo'lmagan yuqori konturi bo'yicha), o'rtadagi kartochka (`.login-box`, qalin, max 18px), Login/Parol maydonlari, Kirish tugmasi, barmoq izi tugmasi, "Ilovani o'rnatish" + ekran pasti (`ground`, 24/36px, to'lqinli). Har 2px ustunda balandlik; qiyalik yumshatiladi (`relax`), chetlarda ingichkalashadi, yumaloq burchaklarda qor turmaydi; chizishda silliqlanadi (dumaloq qor). Ochilganda qor yarmigacha yotgan bo'ladi (`seed`), keyin asta to'ladi. Parcha yuzaning oldidan "uchib o'tishi" mumkin (`p` ehtimoli) — shuning uchun logo va pastki yuzalarga ham yetadi.
- **Tozalash:** sichqoncha harakati yoki barmoq bilan surish (`sweep`) — qor olinadi, parchalari harakat yo'nalishida uchib tushadi; keyin yana to'planadi.
- `prefers-reduced-motion` — kam parcha. Sinov: scratchpad `pwsnow.py` (22: kompyuter + telefon — to'planish, sichqoncha/barmoq bilan tozalash, qayta to'planish, qor ustidan kirish, kirgach to'xtashi), `wksnow.py` (WebKit iPhone).

### v13.19 (2026-11-16) — faqat index.html: TUNGI REJIMDA OQ QOLIB KETADIGAN BLOKLAR
- **Xato:** kompyuterda tungi rejimda To'lov kiritishdagi "O'qituvchilar ulushi" kartasi oppoq, ichidagi fan/o'qituvchi yozuvlari oq (ko'rinmas) bo'lib qolardi; Ko'rinish rejimini bossa — to'g'rilanardi. **Sababi:** karta `style="display:none; background:#f8fafc"` bilan yashirin turadi; `markDark` (v13.13 dan beri) faqat yangi qo'shilgan elementlarni va `class` o'zgarishini kuzatardi — `style` orqali ko'rsatilgan blok bo'yalmay qolardi (yashirin paytda fon boshqacha hisoblanardi). Rejim almashtirilganda to'liq `markDark()` ishlab, to'g'rilanardi.
- **Tuzatish:** MutationObserver endi `style` o'zgarishini ham kuzatadi (`attributeOldValue`) — `display:none` dan ko'rinadigan holatga o'tgan blok shu zahoti bo'yaladi (hamma shunday bloklar uchun). Qo'shimcha: `#paymentAllocationBox` uchun tungi rejimda doimiy CSS (to'q shisha).
- **Ruxsat rejimi kompyuterda siqilib qolardi:** yon menyu `display:none` bo'lgach `.main-col` grid'ning menyu ustuniga (0px yoki 280px) tushib, bo'lim ~58px bo'lib qolardi. Tuzatish: `body.perm-mode #dashboard .main-col { grid-column: 1 / -1 }`. Sinov: scratchpad `permwide.py` (24: 1440/1000 kompyuter + telefon, 6 ta ruxsat bo'limi), `payalloc.py`.

### v13.20 (2026-11-16) — faqat index.html: TARTIBLASH
- **Umumiy jadval** (`getBossTableData` — jadval, telefon kartochkalari, Excel): o'quvchi ismi bo'yicha **alifbo tartibida** (`nameCmp`, `Intl.Collator('uz')` — katta-kichik harf, apostrof farqsiz); bitta o'quvchining to'lovlari — vaqt bo'yicha. Avval kiritilgan vaqt bo'yicha edi.
- **To'lovlar tarixi va admin tarixi** (kompyuter + telefon): **oxirgi kiritilgan to'lov doim eng tepada** (`payNewest` — `id` kamayish tartibida). Avval to'lov sanasi (`timestamp`) bo'yicha edi — rahbar sanani orqaga qo'ysa, yangi to'lov o'rtaga tushib qolardi.
- Sinov: scratchpad `sort1320.py` (7 — orqa sana bilan kiritilgan to'lov tepada, alifbo tartibi, kassa o'zgarmagani).

### v13.21 (2026-11-16) — 🌦️ KUNGA MOSLASH (ob-havo effektlari). backend: main.py, routers/weather.py (yangi) + index.html
- **Backend** `GET /api/weather` (har qanday login): Open-Meteo (bepul, kalitsiz) — faqat SHAHAR koordinatalari yuboriladi; `.env` → `WEATHER_LAT/WEATHER_LON/WEATHER_CITY` (standart Qarshi 38.8606, 65.7891). 10 daqiqa kesh (hamma uchun bitta). WMO kodi → `storm | snow | rain | wind (≥28 km/s) | cloudy | sun | night`. Internet bo'lmasa `{ok:false}` — effekt yo'q.
- **Frontend** (`</body>` oldidagi alohida `<script>`): `WX` (sozlama `localStorage['oxmed_wx_v1']` — `on, mode (auto|rain|storm|sun|wind|snow), sound, vol, power (1 o'rtacha / 2 kuchli), asked`), canvas `#wxCanvas` (z 990, modallardan past, pointer-events:none), faqat dastur ichida (kirish sahifasida va chat ochiqligida yo'q).
  - 🌧️ yomg'ir: kuchli chiziqlar, tomchilar menyular/maydonlar ustida (sirpanib tushadi), ichida suv to'planadi (to'lqinli), pastda ko'lmak + doiralar, sachrash.
  - ⛈️ bulutli: ekran qorayadi, yumshoq bulutlar, chaqmoq (shoxli, porlaydi) + butun ekran yorishadi (ikki marta), momaqaldiroq ovozi masofaga qarab kechikadi. `cloudy` (avto) — kamroq chaqmoq, yomg'irsiz.
  - ☀️ quyosh: bulutlar orasidan mo'ralaydi (yumshoq, ko'zni qamashtirmaydi), nurlar, iliq tus, zarrachalar, qushlar ovozi. Telefonda burchakda. 🌙 tun (avto): yulduzlar, oy, chigirtka.
  - 💨 shamol: barglar, chiziqlar, menyular va ikonkalari tebranadi (CSS `rotate`/`translate` — `transform`ga tegmaydi), "shuuv" ovozi.
  - ❄️ qor: menyular, maydonlar ustida to'planadi (yumaloq burchak egriligiga mos — `s.off`, tik joyda turmaydi `s.cap`), pastda qor uyumi, ba'zi yozuvlarni qor bosadi (`frost`). Ochilganda allaqachon yotgan bo'ladi (`seed`).
  - Sichqoncha / barmoq bilan surilsa — qor, tomchi, suv tozalanadi; maydonga yozilayotganda (`activeElement`) unga hech narsa tushmaydi va fokusda tozalanadi.
  - Ovozlar WebAudio sintez (fayl yo'q): yomg'ir "shitr-shitr", shamol, momaqaldiroq "gumbur" (zarba + gumburlash + past bas), qushlar. Brauzer talabi — birinchi bosishdan keyin yoqiladi.
- **Sozlama** (`wxOpenSettings()` → `#editModal`): Yoqish/O'chirish, 6 tanlov (Kunga moslash — hozirgi ob-havo bilan, Yomg'ir, Bulutli, Quyoshli, Shamolli, Qor), Kuchi, Ovoz + balandligi. Joylari: rahbar/admin Sozlamalar kafeli "🌦️ Kunga moslash" ("Yangi" 30-noyabrgacha), o'qituvchi/xodim Profil kafeli, yo'qlamachi tepa paneli.
- **Birinchi so'rov** (`#wxAsk`): standart O'CHIQ; kirgandan keyin bir marta "Ilovani kunga moslaysizmi?" — Ha → kunga moslash + ovoz; Yo'q → o'chiq. Har qurilmada alohida.
- Sinov: scratchpad `pwwx.py` (32: so'rov, Yo'q, sozlama, 5 effekt × kompyuter/telefon, 55–60 kadr/s), `wxform.py` (maydonlar), `wkwx.py` (WebKit iPhone, yo'qlamachi), `wxcorner.py` (burchaklar).

### v13.22 (2026-11-16) — faqat index.html: KUNGA MOSLASH — kuchaytirildi
- **Bulutlarni tarqatish:** sichqoncha/barmoq bulut ustidan o'tsa — bulut tarqaladi (`c.a` shaffoflik), tagidagi yozuvlar ko'rinadi; ~30 soniyada asta qaytadi (bulutli va quyoshli rejimda).
- **Yomg'ir:** pastdan suv menyulargacha ko'tariladi (`flood`, ekranning 20–24% igacha, to'lqinli, doirachalar); menyular ichida suv yozuvgacha (`WMAX` = balandlikning 45%, ≤64px), katta to'lqinlar; menyular tepasi nam (yaltiroq namlik + osilib, uzilib tushadigan tomchilar `s.drips`). Barmoq/sichqoncha bilan pastdagi suv haydaladi va menyu ichidagi suv kamayadi — keyin yana asta to'ladi.
- **Shamol:** menyulardan tashqari hamma ko'rinib turgan yozuv va element qimirlaydi (`WTEXT_SEL`: jadval kataklari, ismlar, sarlavhalar, tugmalar, maydonlar, belgilar — ko'pi bilan 260 ta, CSS `rotate/translate`); o'chirilganda hammasi joyiga qaytadi.
- **Oq (kunduzgi) rejim:** `LIGHTBG` — qor parchalari och ko'kish (`SNOW_L`), uyumlar kulrang chegara + soya bilan, qor dog'lari (`FROST_L`); yomg'ir chiziqlari, sachrashlar, doirachalar ko'k. O'qituvchi kabinetida — "Yorug'" mavzu bo'lsa.
- Sinov: scratchpad `wx22.py` (20 — bulut tarqatish/qaytish, suv haydash/to'lish, yozuvgacha suv, shamolda matnlar, oq rejim), `pwwx.py` (32), `wxform.py` (15), `pw1312.py` (19).

### v13.23 (2026-11-16) — faqat index.html: SUV QIYALIGI, QO'L BILAN TO'LQIN, BALAND QOR
- **Telefon qiyaligi** (`devicemotion` → `tiltFeed` → `TL`): gravitatsiya ekran koordinatasiga o'giriladi (`screen.orientation.angle` hisobga olinadi; iOS'da belgilar teskari). Pastdagi suv va menyular ichidagi suv yuzasi qiyaligi `TL.slope` (sekin og'adi); telefon teskari qilinsa (`TL.flip`) — suv tepaga oqadi. iPhone (iOS 13+) — ruxsat kerak: yomg'ir paytida birinchi bosishda bir marta so'raladi (`wxTiltAsk`), sozlamada "📱 Telefonni qiyalatish" tugmasi. Kompyuterda qiyalik yo'q (suv tekis).
- **Qo'l/sichqoncha bilan to'lqin:** pastdagi suv yuzasi — 1D to'lqin simulyatsiyasi (`WV`, `waveStep`): qo'l tekkan joyda suv chuqurlashadi, harakat tomonga to'lqin yuguradi; yomg'ir tomchilari ham yuzani qimirlatadi. Menyu ichidagi suvga ham harakat tomonga turtki (`s.kick`).
- **Qor:** pastdagi qor uyumi menyulargacha (`GMAX` = ekranning 18–22%, tepaliklar `gcap`), asta qalinlashadi; qo'l/sichqoncha bilan kuraladi (zarrachalar uchadi).
- Sinov: scratchpad `wxtilt.py` (8 — o'ngga/chapga qiya, teskari, to'lqin, 60 kadr/s), `wxground.py` (6), `pwwx` (32), `wx22` (20), `wxform` (15), `pw1312` (19).

### v13.24 (2026-11-16) — faqat index.html: iPhone/Android'DA JOYLASHUV, SUV CHAYQALISHI
- **Xato (iPhone'da ko'rindi):** qor va suv menyulardan siljib, pastga cho'zilib chizilardi. **Sababi:** canvas o'lchami `innerWidth/innerHeight` dan olinardi — iPhone'da (status bar, xavfsiz zona) bu canvasning haqiqiy balandligiga teng emas, rasm cho'zilardi. **Tuzatish:** o'lcham va joy canvasning o'zidan (`getBoundingClientRect`, `OX/OY` siljish `setTransform` ga), har kadrda tekshiriladi (burish, klaviatura, Safari paneli). Kirish sahifasidagi qorda ham.
- **Suv chayqalishi:** qiyalik prujina kabi (`TL.slope`, `TL.sv`) — asta boshlanadi, ortiqcha borib qaytib tinchiydi; og'ish paytida suv yonboshdan to'lqin bo'lib yuradi (`WV` ga turtki). Teskari qilinsa suv ~0,9 s da bir tomondan ikkinchisiga oqib o'tadi (`TL.side` 0…1, ikkala tomon chiziladi, oqayotgan tomchilar), menyular ichida ham.
- **Burchak:** `window.orientation` (telefonda aniq) birinchi, bo'lmasa `screen.orientation.angle`.
- Oq rejimda qor dog'lari — soyali qor uyumchasi (`FROST_L`), faqat menyu/maydonlarda (katta bo'lim fonida emas).
- Sinov: scratchpad `wx24.py` (18 — iPhone WebKit, siljitilgan canvas, Android: qor menyu tepasiga 0–1 px aniqlikda; chayqalish; teskarida oqib o'tish), `wxflip.py`, va hamma oldingi ob-havo sinovlari.

### v13.25 (2026-11-16) — BUGUNGI TUSHUM, "TO'LOVNI OLDIM", SANA BO'YICHA TARIX. backend: models, main, routers/cash.py (yangi) + index.html
- **Bosh sahifa:** katta kartada tepada "{Oy} oyi tushumi" (shu oy to'lovlari), pastida "💰 Kassadagi sof summa: X so'm"; xarajat yozuvi olib tashlandi (`#dashK3Label`, `#dashAmountSub`). "To'lov foizi" kartasi o'rniga **💵 Bugungi tushum** (`#dashTodayCard`, `#dashToday`, `#dashTodaySub`; telefonda qisqa summa).
- **Bugungi tushum** = bugun (Toshkent) sanasidagi to'lovlar, oxirgi "oldim" tasdig'idan keyingilari (id bo'yicha). `GET /api/cash/today` (rahbar+admin): items (o'quvchi, soat, sinf/fan, oy, summa, usul, kim kiritgan), totals (all/naxt/click/terminal + soni), upto_id, bugungi topshirishlar, can_confirm. Har 30 s va ilovaga qaytganda yangilanadi.
- **Oyna** (`openTodayCash`, `TC`, `renderTodayCash`): tepada Hammasi | Click | Terminal | Naqd (standart — **Naqd**), tanlanganining jami va ro'yxati, bugungi topshirishlar (soat, kim, qancha). **Rahbar:** "✅ Bugungi to'lovni oldim — X so'm" → "Haqiqatan ham … tasdiqlaysizmi?" → `POST /api/cash/handover {upto_id}` (faqat rahbar) → jadval `cash_handovers` → rahbarda ham, adminda ham 0 dan boshlanadi. Oxirgi amallarga yoziladi. **Kassa, to'lovlar, ulushlar, balanslar o'zgarmaydi** (sinovda tekshirilgan).
- **To'lovlar tarixi va admin tarixi:** o'quv yili tanlagichi yonida 📆 sana (`HIST_DAY`, `setHistDay`, `payDay` — Toshkent sanasi): tanlansa — shu kungi to'lovlar, tepada xulosa (soni, jami, naqd, click/terminal, kim nechta kiritgan — `dayBanner`), "✕ Sanani olib tashlash" yoki oy tabi bosilsa — yana oy bo'yicha.
- Sinov: scratchpad `t1325.py` (12 API — usullar, faqat rahbar, 0 ga tushish, ikki marta yo'q, keyingi to'lov, kassa o'zgarmagani), `pw1325.py` (22 brauzer — admin telefon, rahbar kompyuter), pw1311, pw139, t98, pw1312, pwwx, sort1320.

### v13.26 (2026-11-17) — DASTURCHI (yashirin) sahifasi + SMS HISOBINI TO'LDIRISH. backend: models, main, auth, audit, routers/auth, routers/dev.py (yangi) + index.html
- **Yashirin dasturchi login** (Sukhrob uchun): maxfiy login/parol SERVERDAGI `.env` da — `DEV_LOGIN`, `DEV_PASSWORD_HASH` (bcrypt). **Bazada YO'Q** — shuning uchun foydalanuvchilar ro'yxati, chat, "Oxirgi amallar"da hech qachon ko'rinmaydi; borligini ham hech kim bilmaydi. Login: `sukhrob_dev` (parolni Sukhrob biladi — bu yerda yozilmaydi). Oddiy kirish sahifasiga shu login/parol yozilsa — **Dasturchi sahifasi** (`#devPortal`, `DV`, `devOpen/devClose/dvTab`) ochiladi.
- `auth.py`: `ROLE_DEV="Dasturchi"`, `is_dev_login`, `dev_login_ok`, `_dev_user()` (bazaga yozilmaydigan vaqtinchalik User, id=-1), `require_dev` (403 emas, **404** — borligini bildirmaslik uchun). `routers/auth.py` login'da dasturchi shoxi — **audit'ga YOZILMAYDI** (success ham, xato parol ham). `audit.py` SKIP ga `dev` qo'shildi — barcha `/api/dev/*` amallari jurnalga tushmaydi.
- **SMS hisobini to'ldirish:** jadval `sms_topups` (amount, to_eskiz, fee, status pending|done|canceled, by_user/by_who, done_at/by). `Settings` ga: `topup_min` (182000), `topup_fee` (82000), `topup_card`, `topup_card_name`, `topup_telegram` (standart "Sukhrob_Koziboyev"), `feature_flags` (keyingi bosqich — menyu bloklash). `.env`: `DEV_CARD`, `DEV_TELEGRAM`, `DEV_CARD_NAME` (ixtiyoriy — dasturchi sahifasidan ham o'zgartiriladi).
- **Oqim:** rahbar SMS bo'limida "💳 Hisobni to'ldirish" (`openTopupModal`) → summa (eng kam 182000), "Eskiz hisobingizga 100000 so'm tushadi" (jonli hisob `tuCalc`), karta + Telegram ko'rinadi → "To'ladim" (`tuPay` → `POST /api/dev/topup/pay`) → "Chekni yuborish" `@Sukhrob_Koziboyev` Telegram ochiladi. Dasturchi sahifasida kutilmoqda bo'lib turadi → pulni olib Eskiz'ni to'ldiradi → "✅ Eskiz to'ldirildi" (`POST /api/dev/topup/{id}/done`). Hisob: **Eskiz hisobiga = summa − fee** (182000−82000=100000 Eskiz'ga, 82000 dasturchiga, Sukhrobning xizmat haqi).
- API `/api/dev` (hammasi auditsiz): `GET topup/info`, `POST topup/pay` (require_perm("sms") — rahbar/admin), `GET topups`, `POST topup/{id}/done|cancel`, `GET eskiz-balance`, `GET/PUT settings`, `GET whoami` (oxirgi 6 — require_dev). Dasturchi sahifasi: 💳 To'ldirishlar (kutilayotgan+jami xizmat haqi, bajarildi/bekor), 💰 Eskiz balans, ⚙️ Sozlama (karta, egasi, Telegram, min, fee).
- **MUHIM — hisob-kitobga MUTLAQO ta'sir qilmaydi:** topup alohida jadval, kassa/ulush/balans/Payment tegilmaydi (sinovda `Payment.count()==0` tekshirilgan). Login/parolni o'zgartirish (`.env` da yoki keyingi bosqichda DB) va **menyu bloklash/ochish** — 2-bosqich.
- Sinov: scratchpad `t_dev.py` (15 API — dasturchi login/404/audit yashirin, topup oqimi, min, kassa o'zgarmagani), browser pane (dasturchi sahifasi + rahbar oyna skrinshot, JS sintaksis toza).
- **Serverda `.env` ga qo'shish (deploy'dan oldin):** `cat >> /var/www/oxmed/backend/.env` bilan `DEV_LOGIN=sukhrob_dev` va `DEV_PASSWORD_HASH=<bcrypt xesh>` (quoted heredoc, `$` buzilmasin). Yuklanadigan backend: models.py, main.py, auth.py, audit.py, routers/auth.py, routers/dev.py + index.html.

### v13.27 (2026-11-17) — faqat index.html: BOSH SAHIFA "TO'LOVLAR" SONI
- **Xato:** kartada 41, To'lovlar tarixi/Umumiy jadvalda (Noyabr) 39 — karta BARCHA oylar to'lovlarini sanardi (2 tasi boshqa oy uchun kiritilgan). Endi karta "{Oy} to'lovlari" = shu oy+yil soni (`monthPayments.length`), pastida "Barcha oylar: N ta". Kassa/summalar o'zgarmadi.

### v13.28 (2026-11-17) — faqat index.html: PDF HISOBOTLAR + QARZDORLAR/TO'LAMAGANLAR RO'YXATI
- **Sozlamalar → Hisobotlar** (`#reportsSection`) tepasida "📄 PDF hisobotlar" bloki (`#rpPdf`, `RP`, `rpRender` — `updateSystemStats` chaqiradi): oy tanlash (joriy davr + "Barcha oylar"), Hammasi/Maktab/Repetitor, 2 tugma soni va summasi bilan.
- **🔴 Qarzdorlar PDF** (`pdfDebtors(month, type)`, `rpDebtRows`): #, O'quvchi (alifbo, `nameCmp`), Sinf/Fan, Telefon (+998 …), [Oy], To'lagan (yashil), Sanasi (oxirgi to'lov), Qarzi (qizil), Kiritdi; jami qatori. **✅ To'laganlar PDF** (`pdfPaid`, `rpPaidRows`, yotiq A4): o'quvchi bo'yicha jamlangan (bir necha to'lov — "(2 marta)"), Usuli (rangli), qolgan qarz. Umumiy quruvchi `rpBuildPdf`: to'q ko'k sarlavha + logo (`rpLogo`), rangli chiziq, 3 ko'rsatkich kartasi, rangli jadval (jsPDF + autotable — `loadPDF`), har sahifada sarlavha va "Sahifa N / M". Matn `satLat` (lotin-1).
- **Umumiy jadval pastidagi ro'yxatlar** (`#btDebts`, `#btUnpaid`): alifbo tartibida, kartalar (`.ls-box/.ls-row/.ls-card`: raqam, bosh harfli avatar, ism, sinf/fan, bosiladigan telefon; qarzda qizil summa + "to'lagan"), qarzdorlarda "📄 PDF yuklab olish". Ochiq/yopiq holat saqlanadi (`btDebtOpen`, `btUnpaidOpen`). Tungi va kunduzgi rejim, telefon. `DK_SKIP` ga `.rp-pdf`, `.ls-box`.
- Kassa/hisob-kitobga tegilmagan (faqat ko'rsatish). Sinov: browser pane (PDF pdf.js bilan ko'rildi, telefon/kompyuter, 2 rejim).

### v13.29 (2026-11-17) — faqat index.html: ADMINGA PDF HISOBOTLAR
- Admin Sozlamalar papkasida "📄 Hisobotlar — Qarzdorlar va to'laganlar — PDF" kafelini ko'radi (`#menuReports`, `initializeDashboard` admin shoxi). Ichida FAQAT PDF bloki: `body.rp-admin #reportsSection .rp-only-boss { display:none }` — Excel eksportlari, zaxira va tiklash adminga yopiq (rahbarda hammasi avvalgidek). Logout'da `rp-admin` olib tashlanadi.

### v13.30 (2026-11-17) — faqat index.html: PASTKI MENYU — SUYUQ SHISHA (Telegram uslubi)
- **Kapsula** (`#mobileBottomNav`, CSS "v13.30: SUYUQ SHISHA"): tiniq shaffof shisha (yengil gradient, `blur(14px) saturate(200%)`, oq qirra, yuqorida yaltiroq `::after`); tungi — to'q tiniq shisha. Tanlangan yozuv indigo / tungida `#a5b4fc`.
- **Pill** (`.nb-drop`): tugmaning to'liq kengligi va balandligi, `border-radius: 999px`; kunduzgi — oq shisha, tungi — chuqur to'q (rasmdagidek). Joyi va o'lchami JS'dan: `--x`, `--w`, `--sy`.
- **Harakat** (`setupNavDrop` qayta yozildi): ikki chet alohida prujina (`K_LEAD 560`, `K_TRAIL 210`, so'nish 0.62) — oldingi chet tez, orqadagisi kechikadi → yo'lda cho'ziladi (66 → ~160 px), yetganda biroz qisqarib (~61), ~0,4 s da o'z shakliga qaytadi; tezlikda biroz yassilanadi (`--sy` ≥ 0.86). Birinchi chiqishda `pop` (scale) animatsiya. Barmoq bilan surish — pill barmoq ortidan cho'zilib yuradi, qo'yib yuborilganda eng yaqin tugma. To'lov (FAB) tanlansa pill so'nadi. `prefers-reduced-motion` — darhol. O'qituvchi/xodim menyusi (`.tp-nav .nb-drop`) ham shu pill.
- Sinov: browser pane (telefon, 2 rejim, kadrlar bo'yicha kenglik o'lchandi, surish, o'qituvchi menyusi).

### v13.31 (2026-11-17) — faqat index.html: KOMPYUTER (Windows/Mac) MOSLASHUVI, JADVAL USTMA-UST TUSHISHI, PDF'DA TO'LAMAGANLAR
- **Xato (Mac/Windows):** Umumiy jadvalda pastdagi Qarzdorlar/To'lamaganlar ro'yxati ochilsa jadval USTIGA chiqib qolardi — bo'lim balandligi ekranga qotirilgan edi (`fitBossTable` sec.style.height). Endi bo'lim balandligi erkin, faqat **jadvalning o'zi** (`#btTableWrap`) ekranning qolgan qismini egallaydi (min 340px), ro'yxatlar uning ostida — sahifa pastga suriladi. `applyBossTableMode` ham qayta o'lchaydi.
- **Qarzdorlar PDF** (`pdfDebtors`) pastida endi **"TO'LOV QILMAGANLAR — N ta"** bo'limi (to'q sariq; `rpUnpaidRows` — Umumiy jadvaldagi qoida bilan bir xil: shu oy umuman to'lov yo'q; #, F.I. alifbo, Sinf/Fan, Telefon(lar), Oxirgi to'lovi, Qo'shgan) + 4-karta. `rpBuildPdf` ga `o.extra` (ikkinchi jadval, yangi sahifada sarlavha). Hisobotlar tugmasi "Qarzdorlar va to'lamaganlar", Umumiy jadvaldagi ikkala ro'yxatda PDF tugmasi.
- **Kompyuter moslashuvi** (CSS "v13.31: KOMPYUTER"): ingichka yumaloq aylantirish chiziqlari (Windows'dagi qo'pol kulrang o'rniga; tungi rejimga mos), shrift silliqlash; bosh sahifa KPI pastki yozuvlari kesilmaydi (ikki qatorga o'tadi); Umumiy jadval ko'rsatkichlari `auto-fill minmax(158px)` (katta monitorda bitta qatorda); past ekranlarda (≤900px balandlik — 1366×768, 1280×800) ixcham kartalar va sarlavhalar; ≤1500px kenglikda "Tahrirlash uchun katakchani bosing" yashirin; ≤1440px da Jami o'quvchilar jadvali va `.rtable` (tarixlar) ixcham — gorizontal surilmaydi; katta monitorlar: ≥1700 kontent 1580px, ≥2200 1900px + shrift 17.5px, ≥2900 2300px + 20px.
- Sinov: browser pane 1280×720, 1366×768, 1920×1080, 2560×1440 (rahbar va admin, 16 bo'lim — gorizontal toshish yo'q), PDF (5 sahifa, har sahifada sarlavha), telefon o'zgarmagan.

### v13.32 (2026-11-17) — faqat index.html: PASTKI MENYU IKONKALARI, YANGI "TO'LOV", TELEFONDA CHAT CHEKLANGAN
- **Ikonkalar:** pastki menyularda emoji o'rniga chiziqli SVG (`NB_SVG`, `nbSvg(k)`: home, chat, trash, gear, users, userPlus, user, ledger, pay) — rahbar/admin (`renderMobileBottomNav`, `b.svg`) va o'qituvchi/xodim (`#tpNav`, statik SVG). Rang: kulrang → tanlangan indigo (tungi — `#c7d2fe` + yengil nur), tanlanganda chiziq qalinroq.
- **O'rtadagi "To'lov":** gradient "squircle" (50×50, radius 17, yaltiroq tepasi), ichida pul belgisi SVG, burchakda yashil "+" (`.nb-fab-plus`), atrofida halqa (kunduzgi oq / tungi `#161b29`), bosilganda siqiladi, tanlanganda nur halqa.
- **Telefonda chat vaqtincha cheklangan:** `chatPhoneBlocked()` = sensorli ekran (`pointer: coarse` yoki maxTouchPoints) VA kichik ekran (min(screen) < 700) — telefonlar; kompyuter va katta planshet — ochiq. `chatOpen()` boshida tekshiradi → `chatBlockedSheet()` ("Chat vaqtincha cheklangan… kompyuter orqali", "Tushunarli"). Barcha kirish yo'llari (pastki menyu, o'qituvchi menyusi, push bosilishi, `?chat=`, AI) `chatOpen` orqali — hammasi to'xtaydi. `body.chat-blocked`: Chat ikonkasida qizil 🚫 (`.nb-ban`), o'qilmaganlar soni yashirin, ikonka xira. Qayta ochish: `chatOpen` dagi qatorni olib tashlash.
- Sinov: browser pane — telefon (rahbar kunduzgi/tungi, o'qituvchi shaffof: ikonkalar, 🚫, cheklov oynasi), kompyuter 1366×768 (chat ochiladi).

### v13.33 (2026-11-17) — faqat index.html: QARZDORLAR PDF SODDALASHTIRILDI
- `pdfDebtors`: tepadagi ko'rsatkich kartalari olib tashlandi (`stats: []`; `rpBuildPdf` kartalarsiz jadvalni 40 mm dan boshlaydi — `top0`). Qarzdorlar jadvali: #, O'quvchi, Sinf/Fan, Telefon, [Oy], Sanasi, Qarzi, Kiritdi ("To'lagan" yo'q). To'lov qilmaganlar bo'limi: faqat #, O'quvchi, Oxirgi to'lovi (Sinf, Telefon, Qo'shgan yo'q); sarlavhadagi "alifbo tartibida" yozuvi olib tashlandi (tartib o'zi alifbo bo'yicha qoldi). To'laganlar PDF o'zgarmadi.

### v13.34 (2026-11-17) — faqat index.html: QARZDORLAR PDF — FAQAT ISM, SANA, QARZ
- Qarzdorlar jadvali endi: #, O'quvchi, [Oy — "Barcha oylar"da], Sanasi, Qarzi + JAMI (Sinf/Fan, Telefon, Kiritdi olib tashlandi). To'lov qilmaganlar: #, O'quvchi, Oxirgi to'lovi.

## 4. Keyingi vazifalar / tekshirilmaganlar
- [ ] v7.8 `index.html` ni serverga yuklash va telefonda (iPhone + Android) ko'rib chiqish.
- [ ] Barmoq izini **haqiqiy telefonda** sinash (faqat sun'iy qurilmada sinalgan; faqat https://oxmed.uz da ishlaydi).
- [ ] "Umumiy jadval" → "📥 Excel" tugmasini jonli saytda sinash (XLSX kutubxona CDN'dan yuklanadi).
- [ ] Google: 1–3 haftadan keyin `site:oxmed.uz` va "oxmed" qidiruvini tekshirish; Search Console sitemap statusi.
- [ ] Hodimlar oyligi raqamlari avvalgidek ekanini real ma'lumotda tekshirish (migratsiya eski balanslarni o'zgartirmasligi sinovda tasdiqlangan).
- [ ] **XAVFSIZLIK (pasport/rasm/manzil kiritishdan OLDIN — Sukhrob "keyinroq" dedi, 2026-11-13):** SSH kalit + parol bilan kirishni o'chirish (o'zini qulflamaslik uchun avval kalitni sinash), fail2ban, ufw (faqat 22/80/443), 25 ta yangilanish + reboot, kunlik shifrlangan zaxirani boshqa joyga; pasport raqamlarini shifrlash, rasmlarni himoyalangan endpoint orqali berish, kim-kimning ma'lumotini ko'rgani jurnali, o'quvchi/ota-ona sahifasiga SMS-kod bilan kirish, rahbarga 2FA. Qonun: shaxsiy ma'lumotlar O'zbekistondagi serverda (Ahost'dan joylashuvni so'rash), ota-onalar roziligi, davlat reyestri — yurist bilan aniqlash. Tekshiruv buyrug'i (faqat o'qiydi) shu sessiyada berilgan: sshd -T, ufw status, fail2ban, ss -tlnp, Failed password soni.
- [ ] SMS: Eskiz.uz (NTM "OLMOS XATAMOV", sender "Nik" arizasi kutilmoqda) — real SMS yuborish hali ulanmagan (payments.py da izoh bor).
- Foydalanuvchi talablari: telefon va kompyuter ko'rinishi 100% alohida mos, chiroyli, oddiy xodimlar tushunadigan bo'lsin; **hisob-kitobda xato bo'lishi mumkin emas** — har o'zgarishni sinab ko'ring (PostgreSQL'da migratsiya + ssenariy testlari).

## 5. Ishlash qoidalari
- Har o'zgarishdan oldin Mac'dagi faylni zaxiralang; serverda deploy'dan oldin baza zaxirasi (`pg_dump`).
- Kompyuter ko'rinishini buzmang: telefon CSS'i faqat `@media (max-width: 768px)` ichida.
- UI matnlari o'zbek tilida; versiya raqamini (`Pro 7.x`) har yangilanishda oshiring (title, sidebar `sb-foot`, login sahifasi).
- index.html juda katta — o'zgarishlarni aniq qidirib (grep) kiriting, butun faylni qayta yozmang.
