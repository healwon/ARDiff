public class oldV {
    // readable: up to 40 hours at the rate, every hour beyond at 1.5 times the rate (rounded down once)
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        if (hours <= 40) {
            pay = hours * rate;
        }
        else {
            pay = 40 * rate + (hours - 40) * rate * 3 / 2;
        }
        return pay;
    }
}
