import proj4 from "proj4";
import { register } from "ol/proj/proj4";

export const EPSG_3794 = "EPSG:3794";

/** Register the Slovenian national grid (EPSG:3794) in OpenLayers. */
export function registerSIGrid(): void {
  proj4.defs(
    EPSG_3794,
    "+proj=tmerc +lat_0=0 +lon_0=15 +k=0.9999 +x_0=500000 +y_0=-5000000 +ellps=GRS80 +units=m +no_defs",
  );
  register(proj4);
}
