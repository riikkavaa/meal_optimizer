build:
	docker build --tag=meal_optimizer .
	mkdir -p results

run: build
	docker run -v `pwd`/results:/results --rm meal_optimizer