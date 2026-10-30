import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'.',testMatch:'*.spec.mjs',workers:1,timeout:60000,retries:0,
 use:{baseURL:'http://127.0.0.1:8870',viewport:{width:1440,height:1000},screenshot:'only-on-failure',trace:'retain-on-failure',launchOptions:{args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']}},
 webServer:{command:'python -m services.api.server --port 8870',cwd:'../..',url:'http://127.0.0.1:8870/api/health',reuseExistingServer:false,env:{DATABASE_URL:'sqlite:////tmp/frontiersight-browser-fixture.db',APP_BASE_URL:'http://127.0.0.1:8870'}}});
