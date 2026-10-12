import type { JSX } from 'react';

import { Link } from '@tanstack/react-router';

import { LandingView } from '../../components/LandingView';
import { copy } from '../../copy/adminPeople';
import { LANDINGS } from '../../lib/landings';
import './adminPeople.css';
import { MAPPINGS_ROUTE, PEOPLE_ROUTE } from '../paths';

/**
 * The admin area's landing view — SPEC §13's `routes/admin/`.
 *
 * Still the empty console, with a link to each of the two editors built so far:
 * the observability console and the configuration surface (SPEC §6.3) are what
 * this route grows into. Each link carries its page's own heading as its words.
 */
export function AdminLanding(): JSX.Element {
  return (
    <LandingView landing={LANDINGS.admin}>
      <p>
        <Link className="pulse-admin-link" to={PEOPLE_ROUTE}>
          {copy('admin_people.page.people_heading')}
        </Link>
      </p>
      <p>
        <Link className="pulse-admin-link" to={MAPPINGS_ROUTE}>
          {copy('admin_people.page.mappings_heading')}
        </Link>
      </p>
    </LandingView>
  );
}
