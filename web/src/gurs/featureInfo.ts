import Map from "ol/Map";
import TileLayer from "ol/layer/Tile";
import TileWMS from "ol/source/TileWMS";

export async function getFeatureInfoJSON(
  map: Map,
  layer: TileLayer<TileWMS>,
  coordinate: number[],
): Promise<any | null> {
  const source = layer.getSource();
  const view = map.getView();
  const resolution = view.getResolution();
  const projection = view.getProjection();

  if (!source || !resolution || !projection) {
    return null;
  }

  const infoUrl = source.getFeatureInfoUrl(coordinate, resolution, projection, {
    INFO_FORMAT: "application/json",
    FEATURE_COUNT: 10,
  });

  if (!infoUrl) {
    return null;
  }

  try {
    const response = await fetch(`/gurs/proxy?url=${encodeURIComponent(infoUrl)}`);
    if (!response.ok) {
      return null;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return await response.json();
    }

    const text = await response.text();
    return { raw: text };
  } catch (error) {
    console.error("FeatureInfo fetch failed", error);
    return null;
  }
}
