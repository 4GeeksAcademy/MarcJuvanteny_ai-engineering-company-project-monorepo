import Link from "next/link";
import dynamic from "next/dynamic";

const LandingInteractions = dynamic(
  () => import("@/components/landing-interactions").then((mod) => mod.LandingInteractions)
);

export default function Home() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Organization",
            name: "TrackFlow",
            url: "https://trackflow.local",
            description:
              "Empresa de mensajeria y envio de paquetes con foco en puntualidad y cercania.",
            contactPoint: {
              "@type": "ContactPoint",
              contactType: "customer support",
              email: "soporte@trackflow.com",
              telephone: "+34 900 555 123",
            },
          }),
        }}
      />
      <header role="banner">
        <nav id="navbar" aria-label="Navegacion principal">
          <a href="#" className="logo" aria-label="TrackFlow inicio">
            <span className="logo-icon" aria-hidden="true">
              <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                <rect x="0" y="0" width="48" height="48" fill="#d7dbe1" />
                <path d="M6 10H42V22H30V40H18V24L29 16H6Z" fill="#000b2a" />
                <path d="M18 10H30L24 16L18 22Z" fill="#ffffff" />
              </svg>
            </span>
            Track<span>Flow</span>
          </a>
          <ul>
            <li>
              <a href="#servicios">Servicios</a>
            </li>
            <li>
              <a href="#cifras">Resultados</a>
            </li>
            <li>
              <a href="#por-que">Por que nosotros</a>
            </li>
            <li>
              <a href="#testimonios">Clientes</a>
            </li>
            <li>
              <Link href="/application" className="nav-cta">
                Calcular presupuesto
              </Link>
            </li>
          </ul>
        </nav>
      </header>

      <section id="hero">
        <div className="hero-bg" />

        <div className="hero-left">
          <div className="hero-content">
            <div className="hero-badge">Envio express disponible</div>
            <h1>
              Tus envios no viajan,<br />
              <em>vuelan</em> con seguridad.
            </h1>
            <p className="hero-sub">
              No solo movemos paquetes, movemos confianza. Cada entrega lleva consigo
              el compromiso de llegar a tiempo, sin excusas.
            </p>
            <div className="hero-actions">
              <Link href="/application" className="btn-primary">
                Calcula tu presupuesto ahora
              </Link>
              <a href="#servicios" className="btn-ghost">
                Ver servicios
              </a>
            </div>
          </div>
        </div>

        <div className="hero-right">
          <img
            className="hero-photo"
            src="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=1400&q=80"
            alt="Repartidora sonriendo mientras entrega un paquete a un cliente"
          />

          <div className="hero-float">
            <div className="float-card">
              <div className="float-label">Red global</div>
              <div className="float-val">145 paises conectados</div>
            </div>
            <div className="float-card">
              <div className="float-label">Entrega express</div>
              <div className="float-val">En 24-48h en rutas clave</div>
            </div>
            <div className="float-card">
              <div className="float-label">Indice de puntualidad</div>
              <div className="float-val">99.8% lider del sector</div>
            </div>
          </div>
        </div>
      </section>

      <section id="servicios">
        <div className="services-header">
          <div>
            <div className="section-label reveal">Nuestros servicios</div>
            <h2 className="reveal reveal-delay-1">Soluciones a tu medida, no importa el destino.</h2>
            <p className="lead reveal reveal-delay-2">
              Cada envio tiene su historia. Tenemos la solucion perfecta para cada una.
            </p>
          </div>
          <div className="services-img reveal reveal-delay-1">
            <img
              src="https://images.unsplash.com/photo-1553413077-190dd305871c?auto=format&fit=crop&w=1200&q=80"
              alt="Equipo de logistica organizando paquetes en el centro de distribucion"
            />
            <div className="img-overlay-text">+1.200 envios procesados hoy</div>
          </div>
        </div>

        <div className="services-grid">
          <article className="service-card reveal">
            <img src="https://images.unsplash.com/photo-1578575437130-527eed3abbec?auto=format&fit=crop&w=900&q=80" alt="Supervisora controlando envios urgentes en almacen" />
            <h3>Envio Express</h3>
            <p className="service-tagline">Cuando el manana es tarde.</p>
            <p className="service-desc">La maxima prioridad para tus documentos o paquetes urgentes. Recogida en horas, entrega garantizada.</p>
          </article>
          <article className="service-card reveal reveal-delay-1">
            <img src="https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?auto=format&fit=crop&w=900&q=80" alt="Profesional preparando documentacion para envio internacional" />
            <h3>Envio Internacional</h3>
            <p className="service-tagline">Sin fronteras, sin complicaciones.</p>
            <p className="service-desc">Conectamos tu mundo con una logistica simplificada. Aduanas, documentacion y seguimiento incluidos.</p>
          </article>
          <article className="service-card reveal reveal-delay-2">
            <img src="https://images.unsplash.com/photo-1580674285054-bed31e145f59?auto=format&fit=crop&w=900&q=80" alt="Equipo de empresa gestionando distribucion de multiples paquetes" />
            <h3>Logistica para Empresas</h3>
            <p className="service-tagline">Tu socio estrategico de crecimiento.</p>
            <p className="service-desc">Soluciones de distribucion masiva para que tu solo te preocupes de vender. Nosotros gestionamos el resto.</p>
          </article>
        </div>
      </section>

      <div className="photo-strip" aria-label="Galeria fotografica de operaciones">
        <figure className="strip-item" data-caption="Centro logistico Madrid">
          <img src="https://images.unsplash.com/photo-1587293852726-70cdb56c2866?auto=format&fit=crop&w=900&q=80" alt="Almacen con operarios clasificando paquetes" />
        </figure>
        <figure className="strip-item" data-caption="Flota de reparto">
          <img src="https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?auto=format&fit=crop&w=900&q=80" alt="Repartidor amable entregando un paquete en domicilio" />
        </figure>
        <figure className="strip-item" data-caption="Entrega internacional">
          <img src="https://images.unsplash.com/photo-1519003722824-194d4455a60c?auto=format&fit=crop&w=900&q=80" alt="Equipo preparando envios para rutas internacionales" />
        </figure>
        <figure className="strip-item" data-caption="Tracking en tiempo real">
          <img src="https://images.unsplash.com/photo-1556740758-90de374c12ad?auto=format&fit=crop&w=900&q=80" alt="Cliente revisando seguimiento de envio desde su movil" />
        </figure>
      </div>

      <section id="cifras">
        <div className="cifras-inner">
          <div className="cifras-header">
            <div className="section-label reveal">La empresa en cifras</div>
            <h2 className="reveal reveal-delay-1">Nuestra trayectoria<br />se mide en resultados.</h2>
          </div>
          <div className="cifras-grid reveal reveal-delay-2">
            <article className="cifra-item">
              <span className="cifra-number"><span className="counter" data-target="1.2" data-suffix="M+">0</span></span>
              <div className="cifra-label">Paquetes entregados</div>
              <p className="cifra-desc">Miles de historias que llegaron a su destino con exito este ano.</p>
            </article>
            <article className="cifra-item">
              <span className="cifra-number"><span className="counter" data-target="50000" data-suffix="">0</span></span>
              <div className="cifra-label">Clientes activos</div>
              <p className="cifra-desc">Personas y empresas que confian en nosotros para su dia a dia.</p>
            </article>
            <article className="cifra-item">
              <span className="cifra-number"><span className="counter" data-target="145" data-suffix="">0</span></span>
              <div className="cifra-label">Paises conectados</div>
              <p className="cifra-desc">Una red global que elimina las distancias en los 5 continentes.</p>
            </article>
            <article className="cifra-item">
              <span className="cifra-number"><span className="counter" data-target="99.8" data-suffix="%">0</span></span>
              <div className="cifra-label">Puntualidad</div>
              <p className="cifra-desc">Porque sabemos que en logistica, el tiempo es el activo mas valioso.</p>
            </article>
          </div>
        </div>
      </section>

      <section id="testimonios">
        <div className="test-header">
          <div className="section-label reveal">Experiencia de usuario</div>
          <h2 className="reveal reveal-delay-1">Nuestros clientes hablan por nosotros.</h2>
          <p className="lead reveal reveal-delay-2" style={{ marginInline: "auto" }}>
            Cada historia es real. Cada entrega, un compromiso cumplido.
          </p>
        </div>

        <div className="carousel-outer reveal">
          <div className="carousel-track-wrap">
            <div className="carousel-track" id="uxTrack">
              <article className="carousel-slide">
                <div className="carousel-card">
                  <div className="carousel-content">
                    <img className="carousel-media" src="https://images.unsplash.com/photo-1600880292203-757bb62b4baf?auto=format&fit=crop&w=900&q=80" alt="Emprendedora contenta despues de una entrega rapida" />
                    <div>
                      <div className="carousel-stars"><span>★</span><span>★</span><span>★</span><span>★</span><span>★</span></div>
                      <p className="carousel-quote">Increible la rapidez. Pense que mi envio internacional tardaria semanas, pero llego en tres dias y en perfecto estado. Repetire seguro.</p>
                    </div>
                  </div>
                </div>
              </article>
              <article className="carousel-slide">
                <div className="carousel-card">
                  <div className="carousel-content">
                    <img className="carousel-media" src="https://images.unsplash.com/photo-1556740738-b6a63e27c4df?auto=format&fit=crop&w=900&q=80" alt="Consultor siguiendo su envio premium desde el movil" />
                    <div>
                      <div className="carousel-stars"><span>★</span><span>★</span><span>★</span><span>★</span><span>★</span></div>
                      <p className="carousel-quote">La opcion premium vale cada centimo. El seguimiento en tiempo real me dio la tranquilidad que necesitaba para enviar documentos criticos de mi negocio.</p>
                    </div>
                  </div>
                </div>
              </article>
              <article className="carousel-slide">
                <div className="carousel-card">
                  <div className="carousel-content">
                    <img className="carousel-media" src="https://images.unsplash.com/photo-1573496799515-eebbb63814f2?auto=format&fit=crop&w=900&q=80" alt="Cliente satisfecha con la transparencia de precios" />
                    <div>
                      <div className="carousel-stars"><span>★</span><span>★</span><span>★</span><span>★</span><span>★</span></div>
                      <p className="carousel-quote">Lo que mas valoro es la claridad en los precios. Es dificil encontrar una empresa de transporte que sea tan honesta con sus tarifas desde el primer momento.</p>
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <div className="carousel-controls">
            <button className="carousel-btn" id="carouselPrev" type="button" aria-label="Testimonio anterior">‹</button>
            <div className="carousel-dots" id="carouselDots">
              <button className="carousel-dot active" type="button" aria-label="Ir al testimonio 1" />
              <button className="carousel-dot" type="button" aria-label="Ir al testimonio 2" />
              <button className="carousel-dot" type="button" aria-label="Ir al testimonio 3" />
            </div>
            <button className="carousel-btn" id="carouselNext" type="button" aria-label="Siguiente testimonio">›</button>
          </div>

          <div className="carousel-progress" aria-hidden="true">
            <div className="carousel-progress-fill" id="carouselProgress" />
          </div>
        </div>
      </section>

      <section id="cta">
        <div className="cta-inner">
          <div className="section-label reveal" style={{ justifyContent: "center" }}>
            <span style={{ width: "24px", height: "1px", background: "var(--orange)" }} />
            Empieza ahora
          </div>
          <h2 className="reveal reveal-delay-1">Listo para que<br />tus envios vuelen?</h2>
          <p className="lead reveal reveal-delay-2">Calcula tu presupuesto en segundos y recibe una oferta personalizada sin compromiso. Tu primer envio, mas facil que nunca.</p>
          <div className="cta-actions reveal reveal-delay-3">
            <Link href="/application" className="btn-primary">Calcula tu presupuesto ahora</Link>
            <a href="#" className="btn-secondary">Hablar con un asesor</a>
          </div>
        </div>
      </section>

      <footer>
        <div className="footer-bottom">
          <p>© 2026 TrackFlow Logistics S.L. - Todos los derechos reservados.</p>
          <div className="social-links">
            <a href="#">LinkedIn</a>
            <a href="#">Instagram</a>
            <a href="#">Twitter</a>
          </div>
        </div>
      </footer>

      <LandingInteractions />
    </>
  );
}
