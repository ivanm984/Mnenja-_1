import GeoJSON from "ol/format/GeoJSON";
import type Feature from "ol/Feature";
import type Geometry from "ol/geom/Geometry";

import { GURS_CONFIG } from "./gurs.config";
import { EPSG_3794 } from "./proj3794";

const geoJsonFormat = new GeoJSON();

export async function searchParcelKO(
  koId: number,
  stParcel: string,
): Promise<Feature<Geometry>[]> {
  const escapedParcel = stParcel.replace(/'/g, "''");
  const params = new URLSearchParams({
    service: "WFS",
    request: "GetFeature",
    version: "2.0.0",
    typeNames: GURS_CONFIG.layers.PARCELE,
    outputFormat: "application/json",
    srsName: EPSG_3794,
    CQL_FILTER: `KO_ID=${koId} AND ST_PARCELE='${escapedParcel}'`,
  });

  const targetUrl = `${GURS_CONFIG.wfsUrl}?${params.toString()}`;

  try {
    const response = await fetch(`/gurs/proxy?url=${encodeURIComponent(targetUrl)}`);
    if (!response.ok) {
      console.warn("GURS WFS search failed", response.statusText);
      return [];
    }

    const text = await response.text();
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch (error) {
      console.error("Invalid JSON payload from GURS", error);
      return [];
    }

    return geoJsonFormat.readFeatures(data, {
      dataProjection: EPSG_3794,
      featureProjection: "EPSG:3857",
    });
  } catch (error) {
    console.error("Parcel search request failed", error);
    return [];
  }
}
