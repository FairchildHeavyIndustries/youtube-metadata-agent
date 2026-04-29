# [Client Name] — Channel-Level Metadata

This file defines the channel-level metadata applied in Step 7 (`channel.py`). These values replace the existing channel description, keywords, and default language settings.

---

## Default Language

```
default_language: en
```

Set to the primary language of the channel's audience. Use ISO 639-1 codes (`en`, `es`, `fr`, `pt`, etc.).

---

## Channel Description (About section)

Write a 2–4 paragraph description of the channel. This appears in the YouTube About tab and is indexed by Google. Optimize for search terms your target buyers actually use.

Guidelines:
- Lead with what the company does and who it serves
- Mention the geographic market explicitly
- Include 3–5 high-value search terms naturally in the first paragraph
- End with a call to action (website, phone, email)
- Primary language first; you can add a translated version below if relevant

```
[Client Name] is a [industry description] serving [geographic market] since [year]. We specialize in [key products/services] for [target customer types].

[Second paragraph: key differentiators, experience, notable customers or projects if public.]

[Third paragraph (optional): secondary products or services.]

Visítenos en [website] | [phone] | [email]
```

---

## Channel Keywords

Space-separated keyword string applied to `brandingSettings.channel.keywords`. These influence how YouTube categorizes the channel and surface it in related channels.

```
[brand name] [primary product category] [secondary product category] [location] [industry] [target customer type] [key search terms]
```

Example:
```
acme equipment street sweepers vacuum trucks aerial lifts new england municipalities public works contractors heavy equipment dealer
```

Guidelines:
- 10–20 keywords/phrases, space-separated (multi-word phrases are fine)
- Lead with brand name and primary product category
- Include geographic terms your buyers search
- Do not repeat the same word more than twice
- Avoid generic filler terms with no search value ("quality", "best", "leading")
