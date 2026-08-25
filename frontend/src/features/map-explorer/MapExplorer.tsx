import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { apiRequest } from '../../services/api';
import 'maplibre-gl/dist/maplibre-gl.css';

type BoundaryCollection = { type: 'FeatureCollection'; features: Array<{ type: 'Feature'; id: string; geometry: object; properties: { name: string; level: string; boundary_version: string; boundary_source: string } }> };

export function MapExplorer() {
  const container = useRef<HTMLDivElement>(null);
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const styleUrl = import.meta.env.VITE_MAP_STYLE_URL as string | undefined;
  const boundaries = useQuery({ queryKey: ['governed-boundaries'], queryFn: () => apiRequest<BoundaryCollection>('/geography/boundaries'), enabled: authenticated });
  useEffect(() => {
    if (!container.current || !boundaries.data?.features.length) return;
    let cancelled = false; let map: import('maplibre-gl').Map | undefined;
    void import('maplibre-gl').then(({ default: maplibregl }) => {
      if (cancelled || !container.current) return;
      const style = styleUrl ?? { version: 8 as const, sources: {}, layers: [{ id: 'background', type: 'background' as const, paint: { 'background-color': '#071b18' } }] };
      map = new maplibregl.Map({ container: container.current, style, center: [46.2, 5.2], zoom: 4.5 });
      map.addControl(new maplibregl.NavigationControl(), 'top-right');
      map.on('load', () => {
        map?.addSource('governed-boundaries', { type: 'geojson', data: boundaries.data as never });
        map?.addLayer({ id: 'boundary-fill', type: 'fill', source: 'governed-boundaries', paint: { 'fill-color': '#1f6f5c', 'fill-opacity': 0.32 } });
        map?.addLayer({ id: 'boundary-line', type: 'line', source: 'governed-boundaries', paint: { 'line-color': '#72c5a6', 'line-width': 1.4 } });
      });
    });
    return () => { cancelled = true; map?.remove(); };
  }, [boundaries.data, styleUrl]);
  return <main><p className="eyebrow">MAP EXPLORER</p><h1>Governed boundary layers</h1><p className="lead">Only authorized, persisted source geometries are rendered. Boundary version and attribution remain available in the API projection.</p><div className="map" ref={container} aria-label="Somalia governed boundary map">
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Boundary access follows membership geography.</p></div>}
    {authenticated && boundaries.isPending && <div className="empty">Loading governed boundaries…</div>}
    {boundaries.isError && <div className="empty error" role="alert"><b>Boundary layer unavailable</b><p>{boundaries.error.message}</p></div>}
    {boundaries.data?.features.length === 0 && <div className="empty"><b>No approved boundary geometry configured</b><p>Import a licensed, versioned GeoJSON source. Nothing has been fabricated.</p></div>}
  </div><div className="legend"><b>Boundary status</b><span>Authorized geometry</span><span>Versioned source</span><span>No synthetic fallback</span></div></main>;
}
