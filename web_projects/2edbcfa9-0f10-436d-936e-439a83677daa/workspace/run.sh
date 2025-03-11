#!/bin/bash

# Step a: Install dependencies
npm install

# Step b: Run necessary parts of the codebase in parallel
npm run script1 & 
npm run script2 & 
npm run script3 & 

# Wait for all background processes to finish
wait
