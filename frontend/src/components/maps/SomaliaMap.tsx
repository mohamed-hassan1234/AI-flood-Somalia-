/**
 * Somalia risk map.
 *
 * Renders governed administrative boundaries from `/geography/boundaries`,
 * shaded by the risk signal attached to each unit, plus point markers for
 * gauge-scoped domains.
 *
 * Scientific constraint enforced here: a domain is only ever drawn at the
 * geographic scope it is actually modelled at. River-flood intelligence is
 * station-scoped, so it renders as discrete gauge markers — never as a filled
 * polygon over the surrounding district, which would imply inundation extent
 * the platform does not model. Units with no signal are drawn in the neutral
 * "no data" fill rather than being coloured as `normal`, because absence of a
 * prediction is not evidence of low risk.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type {
  GeoJSONSource,
  Map as MapLibreMap,
  Popup as MapLibrePopup,
} from 'maplibre-gl';
import { Layers, Maximize2, Minus, Plus } from 'lucide-react';

import { severity, severityDescriptors, type Severity } from '../../lib/risk';
import { Button, IconButton, Skeleton, cx } from '../ui/primitives';
import type { BoundaryFeatureCollection } from '../../types/api';

import 'maplibre-gl/dist/maplibre-gl.css';

/** Somalia's national extent, used for the initial view and reset control. */
const SOMALIA_BOUNDS: [[number, number], [number, number]] = [
  [40.8, -1.9],
  [51.6, 12.1],
];

/* ------------------------------------------------------------------ types -- */

/** A polygon-scoped unit to shade (district or region). */
export interface MapUnit {
  adminUnitId: string;
  level: Severity;
  /** Primary label shown on hover and selection. */
  name: string;
  /** Optional secondary line, e.g. probability or parent region. */
  detail?: string;
}

/** A point-scoped feature to mark (river gauge). */
export interface MapMarker {
  id: string;
  longitude: number;
  latitude: number;
  level: Severity;
  name: string;
  detail?: string;
}

export interface SomaliaMapProps {
  boundaries: BoundaryFeatureCollection | undefined;
  /** Risk shading keyed by `admin_unit_id`. Units absent here read as "no data". */
  units?: MapUnit[];
  markers?: MapMarker[];
  selectedId?: string | null;
  onSelectUnit?: (adminUnitId: string) => void;
  onSelectMarker?: (markerId: string) => void;
  /** Rendered inside the map frame, above the canvas. */
  overlay?: React.ReactNode;
  loading?: boolean;
  className?: string;
  /** Shown in the legend to state what the shading represents. */
  legendTitle?: string;
  /** Honest statement of the geographic scope currently displayed. */
  scopeNote?: string;
  height?: string;
}

/* ------------------------------------------------------------- component -- */

export function SomaliaMap({
  boundaries,
  units,
  markers,
  selectedId,
  onSelectUnit,
  onSelectMarker,
  overlay,
  loading,
  className,
  legendTitle = 'Risk level',
  scopeNote,
  height = 'h-[420px] sm:h-[520px]',
}: SomaliaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const popupRef = useRef<MapLibrePopup | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [legendOpen, setLegendOpen] = useState(true);

  // Keep the newest interaction handlers reachable from the map's own
  // listeners without tearing the map down on every render.
  const handlersRef = useRef({ onSelectUnit, onSelectMarker });
  handlersRef.current = { onSelectUnit, onSelectMarker };

  const unitIndex = useMemo(() => {
    const index = new Map<string, MapUnit>();
    for (const unit of units ?? []) index.set(unit.adminUnitId, unit);
    return index;
  }, [units]);

  /**
   * GeoJSON with severity attached per feature. MapLibre cannot read from a JS
   * Map at paint time, so the level is baked into feature properties and the
   * paint expression matches on it.
   */
  const shadedCollection = useMemo(() => {
    if (!boundaries?.features?.length) return null;
    return {
      type: 'FeatureCollection' as const,
      features: boundaries.features.map((feature) => {
        const unit = unitIndex.get(String(feature.id));
        return {
          type: 'Feature' as const,
          id: String(feature.id),
          geometry: feature.geometry,
          properties: {
            ...feature.properties,
            adminUnitId: String(feature.id),
            // `none` is distinct from `normal`: no prediction was returned.
            riskLevel: unit ? unit.level : 'none',
            riskName: unit?.name ?? feature.properties?.name ?? 'Unnamed unit',
            riskDetail: unit?.detail ?? '',
          },
        };
      }),
    };
  }, [boundaries, unitIndex]);

  /* ---- map lifecycle ------------------------------------------------- */

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;

    void (async () => {
      try {
        const { default: maplibregl } = await import('maplibre-gl');
        if (cancelled || !containerRef.current) return;

        // A raster basemap is used only when one is configured. Without it the
        // map renders governed boundaries on a plain ground — correct and
        // attribution-safe, rather than silently pulling an unlicensed tile set.
        const styleUrl = import.meta.env.VITE_MAP_STYLE_URL as string | undefined;

        const map = new maplibregl.Map({
          container: containerRef.current,
          style: styleUrl ?? {
            version: 8,
            sources: {},
            layers: [
              {
                id: 'background',
                type: 'background',
                paint: { 'background-color': '#eef1f5' },
              },
            ],
          },
          bounds: SOMALIA_BOUNDS,
          fitBoundsOptions: { padding: 24 },
          attributionControl: false,
        });

        map.addControl(
          new maplibregl.AttributionControl({ compact: true }),
          'bottom-right',
        );
        map.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-left');
        map.dragRotate.disable();
        map.touchZoomRotate.disableRotation();

        map.on('load', () => {
          if (cancelled) return;
          mapRef.current = map;
          setReady(true);
        });

        map.on('error', () => setFailed(true));
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      popupRef.current?.remove();
      popupRef.current = null;
      mapRef.current?.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  /* ---- boundary layers ----------------------------------------------- */

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    const SOURCE = 'admin-boundaries';
    const empty = { type: 'FeatureCollection' as const, features: [] };
    const data = shadedCollection ?? empty;

    const existing = map.getSource(SOURCE);
    if (existing) {
      // MapLibre's `Source` union does not narrow on a property check, so the
      // concrete type is asserted after confirming the source kind.
      if (existing.type === 'geojson') {
        (existing as GeoJSONSource).setData(data);
      }
      return;
    }

    map.addSource(SOURCE, { type: 'geojson', data: data as never, promoteId: 'adminUnitId' });

    // Severity fill. `none` uses a light neutral so "no prediction" is visibly
    // different from NORMAL green.
    map.addLayer({
      id: 'admin-fill',
      type: 'fill',
      source: SOURCE,
      paint: {
        'fill-color': [
          'match',
          ['get', 'riskLevel'],
          'critical', '#f04438',
          'warning', '#ef6820',
          'watch', '#f5b546',
          'normal', '#17b26a',
          'unknown', '#98a2b3',
          '#dfe3e8',
        ],
        'fill-opacity': [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          0.82,
          ['boolean', ['feature-state', 'hover'], false],
          0.7,
          ['==', ['get', 'riskLevel'], 'none'],
          0.35,
          0.58,
        ],
      },
    });

    map.addLayer({
      id: 'admin-line',
      type: 'line',
      source: SOURCE,
      paint: {
        'line-color': [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          '#0d1526',
          '#ffffff',
        ],
        'line-width': [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          2.4,
          ['boolean', ['feature-state', 'hover'], false],
          1.6,
          0.7,
        ],
      },
    });

    /* ---- interaction ------------------------------------------------- */

    let hovered: string | number | undefined;

    const clearHover = () => {
      if (hovered !== undefined) {
        map.setFeatureState({ source: SOURCE, id: hovered }, { hover: false });
        hovered = undefined;
      }
      popupRef.current?.remove();
      map.getCanvas().style.cursor = '';
    };

    map.on('mousemove', 'admin-fill', (event) => {
      const feature = event.features?.[0];
      if (!feature?.id) return;

      if (hovered !== undefined && hovered !== feature.id) {
        map.setFeatureState({ source: SOURCE, id: hovered }, { hover: false });
      }
      hovered = feature.id;
      map.setFeatureState({ source: SOURCE, id: hovered }, { hover: true });
      map.getCanvas().style.cursor = 'pointer';

      // A deliberately small hover card. Full intelligence opens in a panel —
      // the map itself must not become the detail view.
      const level = String(feature.properties?.riskLevel ?? 'none');
      const descriptor = level === 'none' ? null : severity(level);
      const name = String(feature.properties?.riskName ?? '');
      const detail = String(feature.properties?.riskDetail ?? '');

      void import('maplibre-gl').then(({ default: maplibregl }) => {
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 10,
          className: 'somalia-map-popup',
        })
          .setLngLat(event.lngLat)
          .setHTML(
            `<div style="font:500 12px/1.35 Inter,system-ui,sans-serif;color:#0d1526;padding:2px 1px">
               <div style="font-weight:600">${escapeHtml(name)}</div>
               <div style="margin-top:3px;color:#475467">${
                 descriptor
                   ? `${descriptor.glyph} ${descriptor.label}`
                   : 'No prediction available'
               }</div>
               ${detail ? `<div style="margin-top:2px;color:#667085">${escapeHtml(detail)}</div>` : ''}
             </div>`,
          )
          .addTo(map);
      });
    });

    map.on('mouseleave', 'admin-fill', clearHover);

    map.on('click', 'admin-fill', (event) => {
      const feature = event.features?.[0];
      // MapLibre types feature properties as `any`; narrow before use.
      const properties: unknown = feature?.properties;
      const id =
        properties && typeof properties === 'object' && 'adminUnitId' in properties
          ? properties.adminUnitId
          : undefined;
      if (typeof id === 'string') handlersRef.current.onSelectUnit?.(id);
    });
  }, [ready, shadedCollection]);

  /* ---- selection state ------------------------------------------------ */

  const previousSelection = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !map.getSource('admin-boundaries')) return;

    if (previousSelection.current) {
      map.setFeatureState(
        { source: 'admin-boundaries', id: previousSelection.current },
        { selected: false },
      );
    }
    if (selectedId) {
      map.setFeatureState({ source: 'admin-boundaries', id: selectedId }, { selected: true });
    }
    previousSelection.current = selectedId ?? null;
  }, [selectedId, ready]);

  /* ---- gauge markers -------------------------------------------------- */

  const markerObjects = useRef<Array<{ remove: () => void }>>([]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    for (const marker of markerObjects.current) marker.remove();
    markerObjects.current = [];

    if (!markers?.length) return;

    void import('maplibre-gl').then(({ default: maplibregl }) => {
      if (!mapRef.current) return;
      for (const item of markers) {
        if (!Number.isFinite(item.longitude) || !Number.isFinite(item.latitude)) continue;

        const descriptor = severity(item.level);
        const element = document.createElement('button');
        element.type = 'button';
        element.setAttribute(
          'aria-label',
          `${item.name}. ${descriptor.label}. ${item.detail ?? ''}`.trim(),
        );
        element.title = `${item.name} — ${descriptor.label}`;
        element.style.cssText = [
          'width:20px;height:20px;border-radius:999px;cursor:pointer',
          `background:${descriptor.solid}`,
          'border:2.5px solid #fff',
          'box-shadow:0 1px 4px rgba(16,24,40,.35)',
          'display:flex;align-items:center;justify-content:center',
          'font:700 10px/1 Inter,system-ui,sans-serif;color:#fff',
          item.id === selectedId ? 'outline:2.5px solid #0d1526;outline-offset:2px' : '',
        ].join(';');
        // Redundant non-colour encoding on the marker itself.
        element.textContent = descriptor.glyph === '●' ? '' : descriptor.glyph;
        element.addEventListener('click', (event) => {
          event.stopPropagation();
          handlersRef.current.onSelectMarker?.(item.id);
        });

        const marker = new maplibregl.Marker({ element })
          .setLngLat([item.longitude, item.latitude])
          .addTo(mapRef.current);
        markerObjects.current.push(marker);
      }
    });
  }, [markers, ready, selectedId]);

  /* ---- controls -------------------------------------------------------- */

  const resetView = () => {
    mapRef.current?.fitBounds(SOMALIA_BOUNDS, { padding: 24, duration: 500 });
  };

  const legend = useMemo(() => severityDescriptors(), []);
  const showsMarkers = Boolean(markers?.length);

  return (
    <div
      className={cx(
        'relative overflow-hidden rounded-[--radius-lg] bg-[--color-surface-sunken]',
        'ring-1 ring-[--color-line]',
        height,
        className,
      )}
    >
      <div
        ref={containerRef}
        className="absolute inset-0"
        role="application"
        aria-label="Somalia risk map"
      />

      {/* Loading and failure overlays sit above the canvas so the map frame
          never collapses and the layout does not shift. */}
      {(loading || (!ready && !failed)) && (
        <div className="absolute inset-0 flex items-center justify-center bg-[--color-surface-sunken]">
          <div className="flex w-full max-w-xs flex-col gap-2.5 px-6" aria-busy="true">
            <Skeleton className="h-3 w-24 bg-[--color-line]" />
            <Skeleton className="h-40 w-full bg-[--color-line]" />
            <Skeleton className="h-3 w-32 bg-[--color-line]" />
          </div>
        </div>
      )}

      {failed && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[--color-surface] px-6 text-center">
          <p className="text-sm font-semibold text-[--color-ink]">Map could not be displayed</p>
          <p className="max-w-sm text-[13px] leading-5 text-[--color-ink-secondary]">
            The map renderer failed to start in this browser. Risk data remains available in the
            tables on this page.
          </p>
        </div>
      )}

      {ready && !failed && boundaries && boundaries.features.length === 0 && (
        <div className="absolute inset-x-0 top-0 m-3 rounded-[--radius-md] bg-[--color-surface] px-3.5 py-3 text-[13px] leading-5 text-[--color-ink-secondary] shadow-[--shadow-sm] ring-1 ring-[--color-line]">
          <span className="font-semibold text-[--color-ink]">No boundary geometry available.</span>{' '}
          No approved, versioned administrative geometry has been imported for your scope. Nothing
          has been substituted.
        </div>
      )}

      {overlay}

      {/* Zoom / reset controls. */}
      <div className="absolute right-3 top-3 flex flex-col gap-1.5">
        <IconButton
          label="Zoom in"
          size="sm"
          variant="secondary"
          onClick={() => mapRef.current?.zoomIn()}
        >
          <Plus className="size-4" aria-hidden="true" />
        </IconButton>
        <IconButton
          label="Zoom out"
          size="sm"
          variant="secondary"
          onClick={() => mapRef.current?.zoomOut()}
        >
          <Minus className="size-4" aria-hidden="true" />
        </IconButton>
        <IconButton label="Reset to national view" size="sm" variant="secondary" onClick={resetView}>
          <Maximize2 className="size-4" aria-hidden="true" />
        </IconButton>
      </div>

      {/* Legend. Collapsible so it never obstructs a small screen. */}
      <div className="absolute bottom-3 left-3 max-w-[calc(100%-1.5rem)]">
        {legendOpen ? (
          <div className="rounded-[--radius-md] bg-[--color-surface]/95 p-3 shadow-[--shadow-sm] ring-1 ring-[--color-line] backdrop-blur">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-muted]">
                {legendTitle}
              </p>
              <button
                type="button"
                onClick={() => setLegendOpen(false)}
                className="-mr-1 inline-flex min-h-6 items-center rounded-[--radius-xs] px-1 text-[11px] font-medium text-[--color-ink-muted] hover:text-[--color-ink]"
              >
                Hide
              </button>
            </div>
            <ul className="flex flex-col gap-1">
              {legend.map((item) => (
                <li key={item.key} className="flex items-center gap-2">
                  <span
                    className="size-2.5 shrink-0 rounded-[2px]"
                    style={{ background: item.solid }}
                    aria-hidden="true"
                  />
                  <span className="text-[11px] font-medium text-[--color-ink-secondary]">
                    {item.glyph} {item.label}
                  </span>
                </li>
              ))}
              <li className="flex items-center gap-2">
                <span
                  className="size-2.5 shrink-0 rounded-[2px] bg-[--color-muted-line]"
                  aria-hidden="true"
                />
                <span className="text-[11px] font-medium text-[--color-ink-secondary]">
                  No prediction
                </span>
              </li>
            </ul>
            {showsMarkers && (
              <p className="mt-2 border-t border-[--color-line] pt-2 text-[11px] leading-4 text-[--color-ink-muted]">
                Circular markers are individual river gauges. Their severity applies to the gauge,
                not the surrounding area.
              </p>
            )}
            {scopeNote && (
              <p className="mt-2 max-w-[15rem] border-t border-[--color-line] pt-2 text-[11px] leading-4 text-[--color-ink-muted]">
                {scopeNote}
              </p>
            )}
          </div>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setLegendOpen(true)}>
            <Layers className="size-3.5" aria-hidden="true" />
            Legend
          </Button>
        )}
      </div>
    </div>
  );
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}
