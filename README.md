
# ACB Plus/Minus – Fantasy Basketball Game (Backend)

Backend de un juego tipo *fantasy league* basado en la **Liga Endesa (ACB)**, con un sistema de mercado, jornadas, plantillas congeladas y control estricto de reglas.

El proyecto está diseñado con foco en:
- coherencia de estado
- reglas robustas de mercado
- ausencia de “acciones manuales” para el administrador
- facilidad de evolución futura

---

## 🧠 Conceptos clave del juego

- Cada usuario tiene un **equipo de 10 jugadores**
- Presupuesto inicial limitado
- Máximo **2 jugadores por equipo real**
- Restricciones por **posiciones** (BASE / ALERO / PIVOT)
- El mercado **abre y cierra automáticamente** según las jornadas
- Los cambios **no se descuentan hasta que el mercado se cierra**
- El estado del juego avanza solo con el trabajo del *wiki/admin*

---

## 🏗️ Arquitectura general

- **FastAPI**
- **SQLAlchemy ORM**
- Base de datos **SQLite**
- Lógica de dominio separada en servicios

---

## 📁 Estructura del proyecto

```
backend/
├── app/
│   ├── api/routes/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   └── services/
├── Scripts/
└── README.md
```

---

## 🧩 Entidades principales

### SeasonState
Estado global de la temporada (preseason, jornada activa, commits).

### UserSeasonState
Estado individual del usuario (presupuesto, cambios, congelación).

### Roster
- **Base**: equipo oficial congelado
- **Draft**: equipo editable

---

## 🏀 Mercado

El mercado se calcula automáticamente con los fixtures:
- Apertura automática
- Cierre automático
- Sin flags manuales

---

## 🔒 Congelación

- El mercado se cierra globalmente
- Cada usuario se congela individualmente al restaurar 10 jugadores
- Los cambios solo se contabilizan al congelar

---

## 🎯 Validaciones

- Máximo 2 jugadores por equipo real
- Reglas dinámicas por posición
- Validación preventiva (no solo al final)

---

## ▶️ Ejecución

```bash
cd backend
python -m uvicorn app.main:app --reload
```

Swagger:
```
http://127.0.0.1:8000/docs
```

---

## 🚧 Estado del proyecto

✔ Mercado estable  
✔ Jornadas automáticas  
✔ Congelación robusta  
✔ Validaciones completas  

---

## ✍️ Autor

Proyecto desarrollado con foco en claridad, robustez y evolución a largo plazo.
