"""Screenshot and interaction QA against the running host-only HTTPS fixture."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    fixture=json.loads(Path('/tmp/airlunix-console-preview/fixture.json').read_text())
    output=Path(__file__).resolve().parents[1]/'docs/screenshots';output.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        executable=os.environ.get('AIRLUNIX_TEST_CHROMIUM')
        options={'headless':True}
        if executable:options['executable_path']=executable
        browser=await p.chromium.launch(**options)
        context=await browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1100})
        page=await context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(fixture['url']);await page.locator('#login-user').fill(fixture['user'])
        await page.locator('#login-password').fill(fixture['password']);await page.get_by_role('button',name='Sign in securely').click()
        await page.locator('#shell').wait_for(state='visible');await page.wait_for_timeout(3500)
        await page.screenshot(path=str(output/'overview-desktop.png'),full_page=True)
        await page.locator('[data-page="storage"]').click();await page.wait_for_timeout(500)
        assert 'unavailable' in (await page.locator('#storage').inner_text()).lower()
        await page.screenshot(path=str(output/'storage-unavailable.png'),full_page=True)
        await page.locator('[data-page="users"]').click();await page.wait_for_timeout(500)
        await page.locator('#change-password').click();await page.locator('#action-dialog').wait_for(state='visible')
        await page.keyboard.press('Escape');assert not await page.locator('#action-dialog').is_visible()
        await page.locator('[data-page="overview"]').click()
        await page.set_viewport_size({'width':390,'height':844});await page.wait_for_timeout(500)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(output/'overview-mobile.png'),full_page=True)
        await page.locator('#logout').click();await page.locator('#login').wait_for(state='visible')
        assert not errors,errors
        print(json.dumps({'desktop':'1440x1100','mobile':'390x844','javascript_errors':errors,'navigation':'passed','dialog_keyboard':'passed','mobile_horizontal_overflow':False,'screenshots':str(output)}))
        await browser.close()

if __name__=='__main__':asyncio.run(main())
