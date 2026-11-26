public class oldV {
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        if (hours <= 40) {
            pay = hours * rate;
        }
        else {
            pay = 40 * rate + (hours - 40) * (rate * 3 / 2);
        }
        return pay;
    }
}
