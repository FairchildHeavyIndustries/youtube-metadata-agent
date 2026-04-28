# Sweep & Vac — Channel-Level Metadata

This file defines the channel-level metadata that `agent/channel.py` will push to YouTube via the `channels.update` API call. Edit values here, then run the channel push step.

The agent reads the YAML front matter as the structured payload. The Markdown body below is reference notes for human reviewers — it is not pushed to YouTube.

The product line in the description and keywords mirrors the live catalog on sweepandvac.com (products.js, April 2026).

---

```yaml
channel_id_env: YOUTUBE_CHANNEL_ID

branding_settings:
  channel:
    title: "Sweep and Vac Unlimited"

    description: |
      Sweep and Vac Unlimited es el distribuidor #1 en equipos pesados en Puerto Rico, con más de 30 años de experiencia importando, vendiendo, y dando servicio a la maquinaria que mantiene a la isla funcionando.

      Atendemos a municipios, departamentos de bomberos, contratistas, y agencias gubernamentales con una línea completa de equipos especializados:

      • Barredoras de calles (Global Sweepers, Schwarze, PowerBoss, Madvac)
      • Aspiradoras industriales y camiones de succión (Madvac, Minuteman, Vac-Con)
      • Equipos aéreos: camiones pluma, canastas y spider lifts (Versalift, CMC, Elliott, ReachMaster)
      • Vehículos de emergencia y seguridad (Spartan, Malley, Hardboard Guard)
      • Camiones de residuos y reciclaje (Perkins, Wilkens)
      • Podadoras y RC mowers (Spider Mowers, RC Mowers, Orec)
      • Lavadoras a presión (Mystic)
      • Equipos de bacheo y mantenimiento de carreteras (Hot Patch)
      • Limpiadoras de playa (Beach Tech)
      • Restregadoras de pisos industriales (Minuteman)
      • Tabletas y tecnología ruggedizada (Getac, Awesome Lifts)
      • Vehículos eléctricos multiuso (GEM)

      En este canal compartimos demostraciones de equipos en acción, entregas a nuestros clientes, contenido educativo sobre especificaciones y casos de uso, y momentos detrás de cámaras de nuestro almacén en Carolina, Puerto Rico.

      ¿Necesitas un equipo o una demostración? Contáctanos:
      📞 Teléfono: [REPLACE_WITH_CHANNEL_PHONE]
      💬 WhatsApp: [REPLACE_WITH_WHATSAPP_NUMBER]
      🌐 Web: https://sweepandvac.com
      ✉️  Email: [REPLACE_WITH_CHANNEL_EMAIL]

      Sweep and Vac Unlimited — Carolina, Puerto Rico
      #1 en equipos pesados en Puerto Rico

    keywords: >
      "equipo pesado Puerto Rico" "barredora de calles" "aspiradora industrial"
      "camión pluma" "camión vactor" "podadora de taludes" "RC mower"
      "spider mower" "lavadora a presión" "limpiadora de playa"
      "tableta ruggedizada" "camión de residuos" "restregadora de pisos"
      "bomberos Puerto Rico" "municipios Puerto Rico" "obras públicas"
      "Versalift" "Vac-Con" "Schwarze" "Madvac" "Beach Tech" "Getac"
      "Spider Mowers" "RC Mowers" "Orec" "Mystic" "Global Sweepers"
      "Sweep and Vac" "Carolina Puerto Rico"

    default_language: es
    country: PR

  image:
    # Banner and avatar are NOT updated by this agent.
    # Manage images manually in YouTube Studio — the API support for
    # banner uploads is fragile and not worth the engineering risk.
    update: false

  watch:
    # Featured channels and watch page settings are out of scope for v1.
    update: false

unsubscribed_trailer:
  # Set to a video ID once a strong "channel intro" video is identified.
  # Until then, leave null and YouTube will show the most recent upload.
  video_id: null
```

---

## Reference notes (not pushed to YouTube)

### Why these specific keywords

The current channel keywords are `"Sweep, Sweepandvac, Sweepers"` — generic, English-only, and not aligned to actual buyer search behavior or to the live product catalog. The replacement set above does three things:

1. **Spanish-first product categories that match the catalog.** Every Spanish keyword a Puerto Rican municipal buyer would type is represented and corresponds to an actual product line on sweepandvac.com: `barredora de calles`, `aspiradora industrial`, `camión pluma`, `camión vactor`, `podadora de taludes`, `lavadora a presión`, `limpiadora de playa`, `tableta ruggedizada`, `camión de residuos`, `restregadora de pisos`.
2. **Brand names that ARE search terms and match catalog manufacturers.** `Versalift`, `Vac-Con`, `Schwarze`, `Madvac`, `Beach Tech`, `Getac`, `Spider Mowers`, `RC Mowers`, `Orec`, `Mystic Washer` — every one of these is a manufacturer carried in the live catalog and is searched directly by procurement officers who already know what they want.
3. **Geographic and persona qualifiers.** `Puerto Rico`, `municipios Puerto Rico`, `bomberos Puerto Rico`, `obras públicas`, `Carolina Puerto Rico` — these scope the channel to its actual market.

The total keywords field stays under YouTube's 500-character limit. Keywords are quoted because YouTube treats unquoted multi-word strings as separate words.

### Why `default_language: es`

The audit flagged that mixing English and Spanish titles confuses YouTube's audience targeting. Setting the channel's default language to Spanish tells YouTube's algorithm that Spanish-speaking viewers are the primary audience, which improves recommendations within that audience and reduces miscategorization.

### Why `country: PR`

Same logic as default language — this scopes channel-level recommendations and trending behavior to Puerto Rico.

### Placeholders that must be filled before push

Before running `agent/channel.py --approve`, replace:

- `[REPLACE_WITH_CHANNEL_PHONE]` — the phone number currently published on Facebook
- `[REPLACE_WITH_WHATSAPP_NUMBER]` — the WhatsApp Business number (likely the same as the phone number, formatted as a `wa.me` link if possible)
- `[REPLACE_WITH_CHANNEL_EMAIL]` — the customer-facing email if one exists; remove the line entirely if not

The agent will refuse to push a channel description that still contains `[REPLACE_WITH_*]` placeholders. This is a hard guard in `channel.py`.

### Catalog cross-reference

The 12 product categories listed in the description map 1:1 to the categories in `categories.json` and are sourced from `products.js` on the live site. If a category is added or removed from the website catalog, both this file and `categories.json` must be updated. The agent does not auto-sync.

| Category | Manufacturers in current catalog |
|---|---|
| `aereos` | Versalift, CMC, Elliott, ReachMaster |
| `aspiradoras` | Madvac, Minuteman, Vac-Con |
| `barredoras` | Global Sweepers, Schwarze, PowerBoss, Madvac |
| `emergencia` | Spartan, Malley, Hardboard Guard |
| `lavadoras` | Mystic |
| `multiuso` | GEM |
| `pavimento` | Hot Patch |
| `playas` | Beach Tech |
| `podadoras` | Spider Mowers, RC Mowers, Orec |
| `residuos` | Perkins, Wilkens |
| `restregadoras` | Minuteman |
| `tecnologia` | Getac, Awesome Lifts |

### What this agent does NOT change

- **Channel banner image** — manage in YouTube Studio
- **Channel avatar** — manage in YouTube Studio
- **Featured channels / watch page sections** — manage in YouTube Studio
- **Channel handle (`@sweepandvac`)** — already correct
- **Custom URL** — already configured

### Validation checklist (run before push)

The `channel.py` script verifies these before calling `channels.update`:

- [ ] No `[REPLACE_WITH_*]` placeholders remain in any field
- [ ] `description` is under 1,000 characters (YouTube limit)
- [ ] `keywords` field is under 500 characters total
- [ ] `country` is a valid ISO 3166-1 alpha-2 code
- [ ] `default_language` is a valid ISO 639-1 code
- [ ] A backup of the current channel state exists in `output/original_backup_*.json`

If any check fails, the script aborts before making any API call.

### Before/after snapshot for the client report

The `report.py` script will include a side-by-side of the channel-level changes:

| Field | Before | After |
|---|---|---|
| Description | (mostly empty / English only) | Spanish-first About section listing all 12 catalog categories with manufacturers and contact methods |
| Keywords | `Sweep, Sweepandvac, Sweepers` | 27 Spanish-first keywords covering catalog products, brands, geography, and personas |
| Default language | unset | `es` |
| Country | unset / US | `PR` |

This is the single highest-leverage change in the entire metadata project — channel-level signals affect every video on the channel, not just individual uploads.
