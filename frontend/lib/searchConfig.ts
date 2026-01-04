import { SearchFilter, SortItem } from "@/lib/types";

// Filter configuration for CIAN listings
export const filterConfig: SearchFilter[] = [
  {
    id: "current_price",
    name: "Цена (₽)",
    type: "range",
    min: 1000000,
    max: 30000000,
    values: [1000000, 30000000],
    changing: false,
  },
  
  {
    id: "rooms",
    name: "Комнаты",
    type: "check",
    options: [
      { value: "0", label: "Студия", checked: false, operator: "eq" },
      { value: "1", label: "1-комн", checked: false, operator: "eq" },
      { value: "2", label: "2-комн", checked: false, operator: "eq" },
      { value: "3", label: "3-комн", checked: false, operator: "eq" },
      { value: "4", label: "4+", checked: false, operator: "gt" },
    ],
  },
  {
    id: "deal_type",
    name: "Тип сделки",
    type: "check",
    options: [
      { value: "sale", label: "Продажа", checked: true, operator: "eq" },
      { value: "rent", label: "Аренда", checked: false, operator: "eq" },
    ],
  },
  {
    id: "seller_type",
    name: "Продавец",
    type: "check",
    options: [
      { value: "owner", label: "Собственник", checked: false, operator: "eq" },
      { value: "agent", label: "Агент", checked: false, operator: "eq" },
      { value: "developer", label: "Застройщик", checked: false, operator: "eq" },
    ],
  },
  {
    id: "condition_score",
    name: "Состояние (AI)",
    type: "check",
    options: [
      { value: "1", label: "Требует ремонта", checked: false, operator: "eq" },
      { value: "2", label: "Удовлетворительное", checked: false, operator: "eq" },
      { value: "3", label: "Хорошее", checked: false, operator: "eq" },
      { value: "4", label: "Отличное", checked: false, operator: "eq" },
      { value: "5", label: "Евроремонт", checked: false, operator: "eq" },
    ],
  },
  {
    id: "area_total",
    name: "Площадь (м²)",
    type: "range",
    min: 20,
    max: 200,
    values: [20, 200],
    changing: false,
  },
  {
    id: "floor",
    name: "Этаж",
    type: "range",
    min: 2,
    max: 40,
    values: [2, 40],
    changing: false,
  },
];

// Sort configuration for CIAN listings
export const sortItems: SortItem[] = [
  { name: "Недавно добавленные", id: 1, column: "last_seen", ascending: false },
  { name: "Сначала дешевые", id: 2, column: "current_price", ascending: true },
  { name: "Сначала дорогие", id: 3, column: "current_price", ascending: false },
  { name: "Цена за м² ↑", id: 4, column: "price_per_sqm", ascending: true },
  { name: "Площадь ↓", id: 5, column: "area_total", ascending: false },
];
