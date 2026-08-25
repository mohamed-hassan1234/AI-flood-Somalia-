import { expect, test } from '@playwright/test';

const apiPattern = 'http://localhost:8000/api/v1/**';

test('public warning projection is reachable without a bearer token', async ({ page }) => {
  let authorization: string | undefined;
  await page.route(apiPattern, async (route) => {
    authorization = route.request().headers().authorization;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: '11111111-1111-1111-1111-111111111111',
        title: 'Synthetic public drought warning', summary: 'SYNTHETIC / DEVELOPMENT DATA',
        risk_domain: 'drought', risk_level: 'warning', target_period: '2027-Gu',
        admin_unit_id: '22222222-2222-2222-2222-222222222222',
        admin_unit_name: 'Synthetic District', boundary_version: 'synthetic-v1',
        published_at: '2027-01-15T10:00:00Z',
      }]),
    });
  });
  await page.goto('/public-warnings');
  await expect(page.getByRole('heading', { name: 'Synthetic public drought warning' })).toBeVisible();
  await expect(page.getByText('SYNTHETIC / DEVELOPMENT DATA')).toBeVisible();
  expect(authorization).toBeUndefined();
});

test('authenticated executive switches to an authorized regional projection', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('somalia-ai-access-token', 'synthetic-browser-token');
  });
  const observedAuthorization: string[] = [];
  await page.route(apiPattern, async (route) => {
    const request = route.request();
    observedAuthorization.push(request.headers().authorization ?? '');
    const url = new URL(request.url());
    if (url.pathname.endsWith('/dashboard/scopes')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{
          id: '33333333-3333-3333-3333-333333333333', name: 'Synthetic Region',
          level: 'region', boundary_version: 'synthetic-v1',
        }]),
      });
      return;
    }
    const scoped = url.searchParams.has('admin_unit_id');
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        generated_at: '2027-01-15T10:00:00Z',
        boundary_scope: scoped ? 'versioned region aggregation' : 'versioned national aggregation',
        scope_admin_unit_id: scoped ? '33333333-3333-3333-3333-333333333333' : null,
        scope_name: scoped ? 'Synthetic Region' : 'Somalia',
        scope_level: scoped ? 'region' : 'country', boundary_version: scoped ? 'synthetic-v1' : null,
        published_warning_count: scoped ? 1 : 2,
        domains: [
          { domain: 'drought', level: 'watch', admin_units_evaluated: scoped ? 2 : 4,
            target_periods: ['2027-Gu'], source_ids: ['synthetic-source'],
            as_of: '2027-01-15T09:00:00Z', stale: false },
          ...['river_flood', 'flash_flood', 'food_security_deterioration'].map((domain) => ({
            domain, level: null, admin_units_evaluated: 0, target_periods: [], source_ids: [],
            as_of: null, stale: true,
          })),
        ],
      }),
    });
  });
  await page.goto('/');
  await expect(page.getByText('Somalia · country')).toBeVisible();
  await page.getByLabel('Executive geography').selectOption('33333333-3333-3333-3333-333333333333');
  await expect(page.getByText('Synthetic Region · region')).toBeVisible();
  await expect(page.getByText('2 areas evaluated')).toBeVisible();
  expect(observedAuthorization.every((value) => value === 'Bearer synthetic-browser-token')).toBe(true);
});

test('Somali language preference persists across browser navigation', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Language').selectOption('so');
  await expect(page.getByRole('link', { name: 'Guddiga Fulinta' })).toBeVisible();
  await expect(page.getByText('Caddeyn lagu kalsoon yahay.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Luqadda')).toHaveValue('so');
  await expect(page.locator('html')).toHaveAttribute('lang', 'so');
});
