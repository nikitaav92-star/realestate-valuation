import { Pool, QueryResult, QueryResultRow } from 'pg';
import { Listing, SearchFilter, SearchParams } from './types';

interface ListingRow {
  id: number;
  url: string;
  region: number;
  deal_type: string;
  rooms: number;
  area_total: number;
  floor: number;
  address: string;
  seller_type: string;
  lat: number;
  lon: number;
  first_seen: Date;
  last_seen: Date;
  is_active: boolean;
  current_price: number;
  price_per_sqm: number;
  main_photo_url: string | null;
  condition_score: number | null;
  condition_label: string | null;
  ai_analysis: string | null;
}

// Create a PostgreSQL connection pool for CIAN database
const pool = new Pool({
  user: process.env.PG_USER || 'realuser',
  password: process.env.PG_PASS || 'strongpass',
  host: process.env.PG_HOST || 'localhost',
  port: parseInt(process.env.PG_PORT || '5432'),
  database: process.env.PG_DB || 'realdb',
});



function convertRowToListing(row: ListingRow): Listing {
  const roomLabel = row.rooms === 0 ? 'Студия' : `${row.rooms}-комн`;
  const title = `${roomLabel} квартира, ${row.area_total.toFixed(1)} м²`;
  
  return {
    ...row,
    title,
    description: row.ai_analysis || row.address,
    price_formatted: `${(row.current_price / 1000000).toFixed(2)} млн ₽`,
    price: row.current_price,
    date: row.last_seen.toISOString().split('T')[0],
    images: row.main_photo_url ? [{ id: 0, name: '', src: row.main_photo_url, alt: title }] : [],
    details: [
      { 
        name: 'Детали', 
        items: [
          `Комнат: ${roomLabel}`,
          `Площадь: ${row.area_total.toFixed(1)} м²`,
          `Этаж: ${row.floor}`,
          `Цена за м²: ${row.price_per_sqm?.toLocaleString()} ₽`,
          `Продавец: ${row.seller_type}`,
          row.condition_label ? `Состояние: ${row.condition_label} (${row.condition_score}/5)` : null,
        ].filter(Boolean) as string[]
      }
    ],
  }
}

// Function to execute SQL queries
export async function executeQuery<T extends QueryResultRow, U = T>(
  query: string,
  params: any[] = [],
  mapRow?: (row: T) => U
): Promise<U[]> {
  const client = await pool.connect();
  try {
    const result: QueryResult<T> = await client.query(query, params);
    return mapRow ? result.rows.map(mapRow) : (result.rows as unknown as U[]);
  } catch (error) {
    console.error('Database query error:', error);
    throw error;
  } finally {
    client.release();
  }
}

// Get default listings (most recent active listings)
export async function getDefaultListings(limit: number = 12): Promise<Listing[]> {
  const query = `
    SELECT 
      l.*,
      lp.price as current_price,
      ROUND(lp.price / NULLIF(l.area_total, 0)) as price_per_sqm,
      lph.photo_url as main_photo_url,
      CASE 
        WHEN l.ai_condition_score = 1 THEN 'Требует ремонта'
        WHEN l.ai_condition_score = 2 THEN 'Удовлетворительное'
        WHEN l.ai_condition_score = 3 THEN 'Хорошее'
        WHEN l.ai_condition_score = 4 THEN 'Отличное'
        WHEN l.ai_condition_score = 5 THEN 'Евроремонт'
        ELSE NULL
      END as condition_label,
      l.ai_condition_score as condition_score,
      l.ai_condition_analysis as ai_analysis
    FROM listings l
    LEFT JOIN LATERAL (
      SELECT price 
      FROM listing_prices 
      WHERE id = l.id 
      ORDER BY seen_at DESC 
      LIMIT 1
    ) lp ON true
    LEFT JOIN LATERAL (
      SELECT photo_url 
      FROM listing_photos 
      WHERE listing_id = l.id AND is_main = true
      LIMIT 1
    ) lph ON true
    WHERE l.is_active = true
    ORDER BY l.last_seen DESC 
    LIMIT $1
  `;
  return executeQuery<ListingRow, Listing>(query, [limit], (row) => (convertRowToListing(row)));
}


function applyFilters(filters: SearchFilter[], startIndex: number) {
  const conditions: string[] = [];
  const values: any[] = [];
  let index = startIndex;

  filters.forEach(filter => {
    const id = filter.id;
    const type = filter.type;

    if (filter.type === 'check') {
      const checked = filter.options?.filter(option => option.checked);
      const eqValues = checked?.filter(option => option.operator === 'eq').map(option => option.value);
      if (eqValues && eqValues.length > 0) {
        conditions.push(`${id} = ANY($${index})`);
        values.push(eqValues);
        index++;
      }
    } else if (type === 'range') {
      const ranges = filter.values;
      if (ranges && ranges[0] !== filter.min || ranges && ranges[1] !== filter.max) {
        conditions.push(`${id} BETWEEN $${index} AND $${index + 1}`);
        values.push(ranges[0], ranges[1]);
        index += 2;
      }
    }
  });

  return { conditionString: conditions.join(' AND '), filterValues: values };
}

export const getPagination = (page: number, size: number) => {
  const limit = size ? +size : 3;
  const from = page ? page * limit : 0;
  const to = page ? from + size : size;
  return { from, to };
}

export async function search(query: SearchParams) {
  const { from } = getPagination(query.page - 1, 9);
  let baseQuery = `
    SELECT 
      l.*,
      lp.price as current_price,
      ROUND(lp.price / NULLIF(l.area_total, 0)) as price_per_sqm,
      lph.photo_url as main_photo_url,
      CASE 
        WHEN l.ai_condition_score = 1 THEN 'Требует ремонта'
        WHEN l.ai_condition_score = 2 THEN 'Удовлетворительное'
        WHEN l.ai_condition_score = 3 THEN 'Хорошее'
        WHEN l.ai_condition_score = 4 THEN 'Отличное'
        WHEN l.ai_condition_score = 5 THEN 'Евроремонт'
        ELSE NULL
      END as condition_label,
      l.ai_condition_score as condition_score,
      l.ai_condition_analysis as ai_analysis
    FROM listings l
    LEFT JOIN LATERAL (
      SELECT price 
      FROM listing_prices 
      WHERE id = l.id 
      ORDER BY seen_at DESC 
      LIMIT 1
    ) lp ON true
    LEFT JOIN LATERAL (
      SELECT photo_url 
      FROM listing_photos 
      WHERE listing_id = l.id AND is_main = true
      LIMIT 1
    ) lph ON true
  `;
  
  const conditions = ['l.is_active = true'];
  let values = [];
  
  if (query.searchTerm !== '') {
    conditions.push(`to_tsvector(l.address) @@ to_tsquery($${values.length + 1})`);
    values.push(query.searchTerm?.split(/\s+/).join(' | '));
  }
  
  const { conditionString, filterValues } = applyFilters(query.filters, values.length + 1);
  if (conditionString) {
    conditions.push(conditionString);
    values = values.concat(filterValues);
  }
  
  if (conditions.length > 0) {
    baseQuery += ' WHERE ' + conditions.join(' AND ');
  }
  
  const sortColumn = query.sort.column === 'price' ? 'current_price' : query.sort.column;
  baseQuery += ` ORDER BY ${sortColumn} ${query.sort.ascending ? 'ASC' : 'DESC'} LIMIT 20 OFFSET ${from}`;

  return executeQuery<ListingRow, Listing>(baseQuery, values, (row) => (convertRowToListing(row)));
}

export async function getListing(id: string): Promise<Listing | null> {
  const query = `
    SELECT 
      l.*,
      lp.price as current_price,
      ROUND(lp.price / NULLIF(l.area_total, 0)) as price_per_sqm,
      lph.photo_url as main_photo_url,
      CASE 
        WHEN l.ai_condition_score = 1 THEN 'Требует ремонта'
        WHEN l.ai_condition_score = 2 THEN 'Удовлетворительное'
        WHEN l.ai_condition_score = 3 THEN 'Хорошее'
        WHEN l.ai_condition_score = 4 THEN 'Отличное'
        WHEN l.ai_condition_score = 5 THEN 'Евроремонт'
        ELSE NULL
      END as condition_label,
      l.ai_condition_score as condition_score,
      l.ai_condition_analysis as ai_analysis
    FROM listings l
    LEFT JOIN LATERAL (
      SELECT price 
      FROM listing_prices 
      WHERE id = l.id 
      ORDER BY seen_at DESC 
      LIMIT 1
    ) lp ON true
    LEFT JOIN LATERAL (
      SELECT photo_url 
      FROM listing_photos 
      WHERE listing_id = l.id AND is_main = true
      LIMIT 1
    ) lph ON true
    WHERE l.id = $1
  `;
  const results = await executeQuery<ListingRow, Listing>(query, [id], (row) => (convertRowToListing(row)));
  return results.length > 0 ? results[0] : null;
}

export async function getNewListings() {
  const query = `
    SELECT 
      l.*,
      lp.price as current_price,
      ROUND(lp.price / NULLIF(l.area_total, 0)) as price_per_sqm,
      lph.photo_url as main_photo_url,
      CASE 
        WHEN l.ai_condition_score = 1 THEN 'Требует ремонта'
        WHEN l.ai_condition_score = 2 THEN 'Удовлетворительное'
        WHEN l.ai_condition_score = 3 THEN 'Хорошее'
        WHEN l.ai_condition_score = 4 THEN 'Отличное'
        WHEN l.ai_condition_score = 5 THEN 'Евроремонт'
        ELSE NULL
      END as condition_label,
      l.ai_condition_score as condition_score,
      l.ai_condition_analysis as ai_analysis
    FROM listings l
    LEFT JOIN LATERAL (
      SELECT price 
      FROM listing_prices 
      WHERE id = l.id 
      ORDER BY seen_at DESC 
      LIMIT 1
    ) lp ON true
    LEFT JOIN LATERAL (
      SELECT photo_url 
      FROM listing_photos 
      WHERE listing_id = l.id AND is_main = true
      LIMIT 1
    ) lph ON true
    WHERE l.is_active = true
    ORDER BY l.last_seen DESC 
    LIMIT 4
  `;
  return executeQuery<ListingRow, Listing>(query, [], (row) => (convertRowToListing(row)));
}

export async function getAllListings() {
  const query = `SELECT id FROM listings WHERE is_active = true`;
  const rows = await executeQuery<{ id: string }>(query);
  return rows.map(listing => ({ params: { id: `${listing.id}` } }));
}
