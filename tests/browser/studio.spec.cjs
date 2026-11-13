const {test, expect} = require('@playwright/test');
test('project studio lifecycle and mobile layout', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('Server access token').fill('test-only-' + 'x'.repeat(32));
  await page.getByRole('button', {name:'Connect →', exact:true}).click();
  await page.getByRole('button', {name:'Task manager', exact:true}).click();
  await page.getByRole('button', {name:'Generate project →', exact:true}).click();
  await expect(page.getByRole('button', {name:'Download ZIP ↓', exact:true})).toBeVisible();
  await expect(page.locator('#source')).toContainText('Run python main.py');
  await page.getByRole('button', {name:'main.py', exact:true}).click();
  await expect(page.locator('#source')).toContainText("print('Hello')");
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', {name:'Download ZIP ↓', exact:true}).click();
  expect(await (await downloading).failure()).toBeNull();
  await page.setViewportSize({width:390, height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'Delete project', exact:true}).click();
  await expect(page.locator('#notice')).toHaveText('Project deleted.');
  await page.getByRole('button', {name:'Disconnect', exact:true}).click();
  await expect(page.getByLabel('Server access token')).toBeVisible();
  expect(errors).toEqual([]);
});

test('ChatGPT prompt and import with actionable validation errors', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('Server access token').fill('test-only-' + 'x'.repeat(32));
  await page.getByRole('button', {name:'Connect →', exact:true}).click();
  await page.getByLabel('Generation method').selectOption('chatgpt');
  await page.getByLabel('Project brief').fill('Build a Python greeting application');
  await page.getByRole('button', {name:'Prepare ChatGPT prompt →'}).click();
  await expect(page.getByLabel('1. Copy this prompt into ChatGPT')).toHaveValue(/Build a Python greeting application/);
  await page.getByLabel('2. Paste the complete JSON response').fill('{broken');
  await page.getByRole('button', {name:'Validate and import project →'}).click();
  await expect(page.locator('#notice')).toContainText('Invalid JSON');
  const project = {name:'Imported greeting', description:'Say hello', techstack:'Python', files:[
    {path:'main.py',content:"print('Hello, Sanket!')"},
    {path:'README.md',content:'Run python main.py'},
  ]};
  await page.getByLabel('2. Paste the complete JSON response').fill('```json\n' + JSON.stringify(project) + '\n```');
  await page.getByRole('button', {name:'Validate and import project →'}).click();
  await expect(page.locator('#project-name')).toHaveText('Imported greeting');
  await expect(page.locator('#stage')).toHaveText('IMPORTED');
  await page.getByRole('button', {name:'main.py', exact:true}).click();
  await expect(page.locator('#source')).toContainText('Hello, Sanket!');
  await page.reload();
  await expect(page.getByLabel('Server access token')).toBeVisible();
  await page.getByLabel('Server access token').fill('test-only-' + 'x'.repeat(32));
  await page.getByRole('button', {name:'Connect →', exact:true}).click();
  await page.locator('#history button').filter({hasText:'Build a Python greeting application'}).click();
  await expect(page.locator('#project-name')).toHaveText('Imported greeting');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
