import TileLayer from "ol/layer/Tile";
import TileWMS from "ol/source/TileWMS";

import { GURS_CONFIG } from "./gurs.config";

/** Create a tiled WMS layer that proxies requests through the backend. */
export function makeKatasterWms(layerName: string): TileLayer<TileWMS> {
  const source = new TileWMS({
    url: GURS_CONFIG.inspireWmsDtmUrl,
    params: {
      LAYERS: layerName,
      TILED: true,
    },
    transition: 0,
    crossOrigin: "anonymous",
  });

  const baseTileLoad = source.getTileLoadFunction();
  source.setTileLoadFunction((tile, src) => {
    const proxiedSrc = `/gurs/proxy?url=${encodeURIComponent(src)}`;
    baseTileLoad(tile, proxiedSrc);
  });

  return new TileLayer({ source });
}
