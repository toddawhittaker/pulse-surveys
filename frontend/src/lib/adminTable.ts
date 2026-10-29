/**
 * The vocabulary the admin's two tables share with their calls: which table an
 * import or export is for, and which column and direction a read asks for.
 *
 * They are the frontend's own words rather than wire shapes (the server takes
 * them as query values), so they live here and not in `../api/admin.ts`, whose
 * exported types are the generated wire's.
 */

/** Which table an import or export belongs to. */
export type Table = 'people' | 'mappings';

/** The columns each table sorts by. */
export type PeopleSort = 'name' | 'category';
export type MappingSort = 'name' | 'course';

/** The direction of a sort. */
export type Order = 'asc' | 'desc';
