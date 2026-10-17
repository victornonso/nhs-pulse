import {test,expect} from '@playwright/test';
for(const screen of ['overview','emergency','capacity','trusts','geography','forecasting','analyst','operations']){
 test(`${screen} publishes a responsive analytical workspace`,async({page},info)=>{
  await page.goto('/'+screen);await expect(page.locator('h1')).toBeVisible();await expect(page.locator('.release-strip')).toBeVisible();
  await expect(page.getByText('Independent analysis using published NHS England statistics.')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:`test-results/${screen}-${info.project.name}.png`});
 });
}
test('filter, trust drill-down, keyboard dismissal and export',async({page})=>{
 await page.goto('/trusts');await expect(page.locator('.release-strip')).toBeVisible();
 await page.getByLabel('Search trusts').fill('R0A');await expect(page.locator('.trust-name')).toHaveCount(1);
 await page.locator('.trust-name').click();await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Export CSV',exact:true}).click();expect((await download).suggestedFilename()).toContain('trusts');
});
