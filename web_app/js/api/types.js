/**
 * Общие типы данных каталога анкет.
 * Используются только для JSDoc-подсказок, во время выполнения ничего не экспортируется.
 */

/**
 * @typedef {'image' | 'video'} MediaType
 */

/**
 * @typedef {Object} GalleryItem
 * @property {MediaType} type
 * @property {string} [src]      Адрес изображения (для type: 'image').
 * @property {string} [poster]   Постер видео (для type: 'video').
 * @property {string} caption
 * @property {string} [duration] Подпись длительности, например '0:42'.
 */

/**
 * @typedef {Object} PlayerStats
 * @property {number} points
 * @property {number} globalRank
 * @property {number} teamRank
 * @property {number} hours
 * @property {number} mapsFinished
 * @property {number} bestRank
 * @property {string} favoriteMap
 * @property {number} joinedYear
 * @property {number} lastSeenHoursAgo
 */

/**
 * @typedef {Object} PlayerRecord
 * @property {string} id
 * @property {string} nick
 * @property {string} initials
 * @property {string} tagline
 * @property {string} description
 * @property {boolean} approved  Признак одобрения модерацией. Наружу отдаются только true.
 * @property {boolean} online
 * @property {string} [currentServer] Текущий сервер, если игрок онлайн.
 * @property {string} [currentMap] Текущая карта, если игрок онлайн.
 * @property {string} region
 * @property {string[]} badges
 * @property {PlayerStats} stats
 * @property {string} cover
 * @property {GalleryItem[]} gallery
 */

/**
 * @typedef {Object} PlayerSummary
 * @property {string} id
 * @property {string} nick
 * @property {'boy' | 'girl'} gender
 * @property {string} initials
 * @property {string} tagline
 * @property {boolean} online
 * @property {string} region
 * @property {string} cover
 * @property {string[]} badges
 * @property {number} lastSeenHoursAgo
 * @property {{points: number, globalRank: number, mapsFinished: number, hours: number}} stats
 */

/**
 * @typedef {Object} PlayerListParams
 * @property {string} [query]
 * @property {'default' | 'points' | 'maps'} [sort]
 * @property {'' | 'boy' | 'girl'} [gender]
 * @property {number} [page]
 * @property {number} [pageSize]
 * @property {AbortSignal} [signal]
 */

/**
 * @typedef {Object} PlayerListResult
 * @property {PlayerSummary[]} items
 * @property {number} total
 * @property {number} page
 * @property {number} pageSize
 * @property {boolean} hasMore
 */

export {};
