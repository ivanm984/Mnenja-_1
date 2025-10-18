import type { WorkSheet } from 'xlsx';
import { read, utils } from 'xlsx';

function filledCell(value: unknown): boolean {
  return value !== '' && value !== null && value !== undefined;
}

function sheetToFilteredAoA(sheet: WorkSheet): string[][] {
  const json = utils.sheet_to_json<string[]>(sheet, {
    header: 1,
    blankrows: false,
    defval: ''
  });

  const filtered = json.filter((row) => row.some(filledCell));
  let headerIndex = filtered.findIndex((row, index) => {
    const current = row.filter(filledCell).length;
    const next = filtered[index + 1]?.filter(filledCell).length ?? 0;
    return current >= next;
  });

  if (headerIndex === -1 || headerIndex > 25) {
    headerIndex = 0;
  }

  return filtered.slice(headerIndex);
}

export function extractCsvFromXlsx(base64: string): string {
  const workbook = read(base64, { type: 'base64' });
  const sheetName = workbook.SheetNames[0];
  const sheet = workbook.Sheets[sheetName];
  const filteredAoA = sheetToFilteredAoA(sheet);
  const normalizedSheet = utils.aoa_to_sheet(filteredAoA);
  return utils.sheet_to_csv(normalizedSheet, { header: 1 });
}
