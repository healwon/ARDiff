public class specV {
    // spec: the old rule, but on a holiday every hour is paid at twice the rate
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        if (hours <= 40) {
            pay = hours * rate;
        }
        else {
            pay = 40 * rate + (hours - 40) * rate * 3 / 2;
        }
        if (holiday == 1) {
            pay = hours * rate * 2;
        }
        return pay;
    }
}
