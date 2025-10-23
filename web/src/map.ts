import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import OSM from "ol/source/OSM";
import { fromLonLat } from "ol/proj";
import type Feature from "ol/Feature";
import type Geometry from "ol/geom/Geometry";

import { registerSIGrid } from "./gurs/proj3794";
import { makeKatasterWms } from "./gurs/wmsLayer";
import { searchParcelKO } from "./gurs/wfsSearch";
import { GURS_CONFIG } from "./gurs/gurs.config";

registerSIGrid();

const baseLayer = new TileLayer({
  source: new OSM(),
});

const parcelLayer = makeKatasterWms(GURS_CONFIG.layers.PARCELE);

export const map = new Map({
  target: "map",
  layers: [baseLayer, parcelLayer],
  view: new View({
    center: fromLonLat([14.505751, 46.056946]),
    zoom: 12,
  }),
});

export async function locateParcel(
  koId: number,
  st: string,
): Promise<Feature<Geometry> | null> {
  const features = await searchParcelKO(koId, st);
  if (!features.length) {
    return null;
  }

  const feature = features[0];
  const geometry = feature.getGeometry();
  if (!geometry) {
    return null;
  }

  map.getView().fit(geometry, {
    maxZoom: 18,
    padding: [30, 30, 30, 30],
  });

  return feature;
}
