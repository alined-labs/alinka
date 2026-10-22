/*
 * The showcase page, at / in Spanish and /en in English: what Alinka is and what it measured,
 * for someone who has a minute, with the way into the frozen demo. Designed with Hallmark
 * (styles/showcase.css carries the stamp) on Alinka's own tokens, so it reads as the same product
 * as the app screens behind it. It fetches nothing: every word and figure comes from
 * lib/showcase-copy.ts, so the prerendered HTML is the whole page.
 */

import { ArrowRight, ArrowUpRight } from "lucide-react";
import type { CSSProperties } from "react";
import { Link } from "react-router";

import { AlinkaLogo } from "~/components/brand/AlinkaLogo";
import { COPY, type Lang, LINKS, MEDIA } from "~/lib/showcase-copy";
import { BOARD_PATH } from "~/lib/view";
import "~/styles/showcase.css";

/**
 * Where the three numbered pins sit on the board capture, in percent of its width and height:
 * the decision counts, the first card's reason, and the document quote in a pending card.
 */
const PINS = [
  { x: "26%", y: "10%" },
  { x: "1.6%", y: "50%" },
  { x: "68.6%", y: "52%" },
] as const;

/** srcset width descriptors for one theme's capture (1136 and 2272 px wide). */
const boardSrcSet = (shot: { x1: string; x2: string }) => `${shot.x1} 1136w, ${shot.x2} 2272w`;
const BOARD_SIZES = "(min-width: 72rem) 70rem, calc(100vw - 2rem)";

export function Showcase({ lang }: { lang: Lang }) {
  const t = COPY[lang];
  const home = lang === "es" ? "/" : "/en";

  return (
    <div className="sc">
      <a href="#contenido" className="ak-sr focus:not-sr-only focus:absolute focus:z-10 focus:bg-surface focus:p-2">
        {t.nav.skip}
      </a>

      <header className="sc-wrap sc-nav">
        <Link to={home} className="sc-nav__brand" aria-label={t.nav.home}>
          <AlinkaLogo />
        </Link>
        <div className="sc-nav__end">
          <Link to={t.nav.switchHref} className="sc-nav__lang" hrefLang={t.nav.switchLang} lang={t.nav.switchLang}>
            {t.nav.switchLabel}
          </Link>
          <Link to={BOARD_PATH} className="ak-btn ak-btn--secondary sc-cta">
            {t.nav.cta}
          </Link>
        </div>
      </header>

      <main id="contenido">
        <section className="sc-wrap sc-hero" aria-labelledby="sc-title">
          <h1 id="sc-title" className="sc-hero__title">
            <span className="sc-hero__figure">{t.hero.figure}</span>{" "}
            <span className="sc-hero__words">{t.hero.headline}</span>
          </h1>
          <div className="sc-hero__side">
            <p className="sc-hero__qualifier">{t.hero.qualifier}</p>
            <p className="sc-hero__lede">{t.hero.lede}</p>
            <div className="sc-ctas">
              <Link to={BOARD_PATH} className="ak-btn ak-btn--primary sc-cta">
                {t.hero.primary}
                <ArrowRight aria-hidden className="ak-icon" />
              </Link>
              <a href={LINKS.repo} className="ak-btn ak-btn--secondary sc-cta">
                {t.hero.secondary}
                <ArrowUpRight aria-hidden className="ak-icon" />
              </a>
            </div>
          </div>
        </section>

        <section className="sc-wrap sc-section" aria-labelledby="sc-spec">
          <h2 id="sc-spec" className="sc-h2">
            {t.spec.title}
          </h2>
          <dl className="sc-spec" aria-labelledby="sc-spec">
            {t.spec.rows.map((row) => (
              <div key={row.label} className="sc-spec__row">
                <dt>{row.label}</dt>
                <dd className="sc-spec__value">{row.value}</dd>
                <dd className="sc-spec__note">{row.note}</dd>
              </div>
            ))}
          </dl>
          <p className="sc-source">
            <span>{t.spec.source}</span>
            <Link to="/evaluacion" className="sc-link">
              {t.spec.link}
              <ArrowRight aria-hidden className="ak-icon" />
            </Link>
          </p>
        </section>

        <section className="sc-wrap sc-section sc-steps" aria-labelledby="sc-steps">
          <div className="sc-steps__head">
            <h2 id="sc-steps" className="sc-h2">
              {t.steps.title}
            </h2>
            <Link to="/como-funciona" className="sc-link">
              {t.steps.link}
              <ArrowRight aria-hidden className="ak-icon" />
            </Link>
          </div>
          <ol className="sc-steps__list">
            {t.steps.items.map((step, i) => (
              <li key={step.title} className="sc-step">
                <span className="sc-step__n" aria-hidden>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="sc-step__title">{step.title}</h3>
                <p className="sc-step__text">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="sc-wrap sc-section" aria-labelledby="sc-video">
          <h2 id="sc-video" className="sc-h2">
            {t.video.title}
          </h2>
          <figure className="sc-figure">
            {/* preload="none": the 6.7 MB file loads only when someone presses play; the poster shows until then. */}
            <video
              className="sc-video"
              controls
              playsInline
              preload="none"
              poster={MEDIA.video.poster}
              width={MEDIA.video.width}
              height={MEDIA.video.height}
              aria-describedby="sc-video-caption"
            >
              <source src={MEDIA.video.src} type="video/mp4" />
              <a href={MEDIA.video.src}>{t.video.fallback}</a>
            </video>
            <figcaption id="sc-video-caption" className="sc-caption">
              {t.video.caption}
            </figcaption>
          </figure>
        </section>

        <section className="sc-wrap sc-section" aria-labelledby="sc-demo">
          <div className="sc-demo__head">
            <h2 id="sc-demo" className="sc-h2">
              {t.demo.title}
            </h2>
            <div className="sc-demo__text">
              <p>{t.demo.text}</p>
              <Link to={{ pathname: BOARD_PATH, search: "?vista=canonica" }} className="ak-btn ak-btn--secondary sc-cta">
                {t.demo.cta}
                <ArrowRight aria-hidden className="ak-icon" />
              </Link>
            </div>
          </div>
          <figure className="sc-figure sc-shot">
            <div className="sc-shot__frame">
              <picture>
                <source
                  media="(prefers-color-scheme: dark)"
                  srcSet={boardSrcSet(MEDIA.board.dark)}
                  sizes={BOARD_SIZES}
                  width={MEDIA.board.width}
                  height={MEDIA.board.height}
                />
                <img
                  src={MEDIA.board.light.x1}
                  srcSet={boardSrcSet(MEDIA.board.light)}
                  sizes={BOARD_SIZES}
                  width={MEDIA.board.width}
                  height={MEDIA.board.height}
                  alt={t.demo.alt}
                  loading="lazy"
                  decoding="async"
                />
              </picture>
              {PINS.map((pin, i) => (
                <span key={pin.x} className="sc-pin" style={{ "--x": pin.x, "--y": pin.y } as CSSProperties} aria-hidden>
                  {i + 1}
                </span>
              ))}
            </div>
            <figcaption>
              <ol className="sc-legend">
                {t.demo.callouts.map((callout) => (
                  <li key={callout}>{callout}</li>
                ))}
              </ol>
            </figcaption>
          </figure>
        </section>
      </main>

      <footer className="sc-wrap sc-foot">
        <p className="sc-foot__line">{t.foot.statement}</p>
        <div className="sc-foot__meta">
          <AlinkaLogo className="sc-foot__logo" />
          <ul className="sc-foot__items">
            {t.foot.items.map((item) => (
              <li key={item.text}>{item.href ? <a href={item.href}>{item.text}</a> : item.text}</li>
            ))}
            <li>
              {t.foot.credit} <a href={LINKS.author}>{t.foot.author}</a>
            </li>
            <li>
              <a href={LINKS.repo}>{t.foot.code}</a>
            </li>
          </ul>
        </div>
      </footer>
    </div>
  );
}
